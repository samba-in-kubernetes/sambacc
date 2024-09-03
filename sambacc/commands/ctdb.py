#
# sambacc: a samba container configuration tool
# Copyright (C) 2021  John Mulligan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#

import argparse
import contextlib
import logging
import os
import socket
import sys
import typing

from sambacc import ctdb
from sambacc import jfile
from sambacc import rados_opener
from sambacc import samba_cmds
from sambacc.simple_waiter import Sleeper, Waiter

from .cli import best_leader_locator, best_waiter, commands, Context, Fail

_logger = logging.getLogger(__name__)

# Rather irritatingly, k8s does not have a simple method for passing the
# ordinal index of a stateful set down to the containers. This has been
# proposed but not implemented yet. See:
#  https://github.com/kubernetes/kubernetes/issues/40651
# While I find putting any k8s specific knowledge in sambacc distasteful
# all we're really doing is teaching sambacc how to extract the node
# number from the host name, an operation that's not k8s specific.
# That isn't *too* dirty. Just a smudge really. :-)
_AFTER_LAST_DASH = "after-last-dash"


def _ctdb_ok():
    sambacc_ctdb = os.environ.get("SAMBACC_CTDB")
    gate = "ctdb-is-experimental"
    if sambacc_ctdb == gate:
        return
    print("Using CTDB with samba-container (sambacc) is experimental.")
    print("If you are developing or testing features for sambacc please")
    print("set the environment variable SAMBACC_CTDB to the value:")
    print("    ", gate)
    print("before continuing and try again.")
    print()
    raise Fail(gate)


def _ctdb_migrate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dest-dir",
        default=ctdb.DB_DIR,
        help="Specify where CTDB database files will be written.",
    )
    parser.add_argument(
        "--archive",
        help="Move converted TDB files to an archive dir.",
    )


def _ctdb_general_node_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--hostname",
        help="Specify the host name for the CTDB node",
    )
    parser.add_argument(
        "--node-number",
        type=int,
        help="Expected node number",
    )
    # This is a choice with a single acceptable param, rather than an on/off
    # bool, # in the case that other container orchs have a similar but not
    # quite the same issue and we want to support a different scheme someday.
    parser.add_argument(
        "--take-node-number-from-hostname",
        choices=(_AFTER_LAST_DASH,),
        help=(
            "Take the node number from the given host name following"
            " the specified policy."
        ),
    )
    parser.add_argument(
        "--take-node-number-from-env",
        "-E",
        const="NODE_NUMBER",
        nargs="?",
        help=(
            "Take the node number from the environment. If specified"
            " with a value, use that value as the environment variable"
            " name. Otherwise, use environment variable NODE_NUMBER."
        ),
    )
    parser.add_argument(
        "--persistent-path",
        help="Path to a persistent path for storing nodes file",
    )
    parser.add_argument(
        "--metadata-source",
        help=(
            "Specify location of cluster metadata state-tracking object."
            " This can be a file path or a URI-style identifier."
        ),
    )


def _ctdb_set_node_args(parser: argparse.ArgumentParser) -> None:
    _ctdb_general_node_args(parser)
    parser.add_argument(
        "--ip",
        help="Specify node by IP",
    )


class NodeParams:
    _ctx: Context
    node_number: typing.Optional[int] = None
    hostname: typing.Optional[str] = None
    persistent_path: str = ""
    _nodes_json: str = ""
    _cluster_meta_uri: str = ""
    _ip_addr: typing.Optional[str] = None
    _cluster_meta_obj: typing.Optional[ctdb.ClusterMeta] = None
    _waiter_obj: typing.Optional[Waiter] = None

    def __init__(self, ctx: Context):
        self._ctx = ctx
        ccfg = ctx.instance_config.ctdb_config()

        # stuff that many of the commands use
        self.persistent_path = ctx.cli.persistent_path
        if self.persistent_path is None:
            self.persistent_path = ccfg["nodes_path"]
        # nodes_json will now only be in the ctdb config section if it has been
        # specified by the user.
        self._nodes_json = ccfg.get("nodes_json") or ""
        # cluster_meta_uri can be a uri-ish string or path. It will be set with
        # a default value by the config even if there's no user supplied value.
        self._cluster_meta_uri = ccfg.get("cluster_meta_uri") or ""

        self.hostname = ctx.cli.hostname
        if ctx.cli.node_number is not None:
            if ctx.cli.node_number < 0:
                raise ValueError(f"invalid node number: {ctx.cli.node_number}")
            self.node_number = ctx.cli.node_number
        elif ctx.cli.take_node_number_from_hostname == _AFTER_LAST_DASH:
            if not self.hostname:
                raise ValueError(
                    "--hostname required if taking node number from host name"
                )
            if "-" not in self.hostname:
                raise ValueError(
                    f"invalid hostname for node number: {self.hostname}"
                )
            self.node_number = int(self.hostname.rsplit("-")[-1])
        elif ctx.cli.take_node_number_from_env:
            try:
                self.node_number = int(
                    os.environ[ctx.cli.take_node_number_from_env]
                )
            except (KeyError, ValueError):
                raise ValueError(
                    "failed to get node number from environment var"
                    f" {ctx.cli.take_node_number_from_env}"
                )
        else:
            self.node_number = None

    @property
    def node_ip_addr(self) -> str:
        if self._ip_addr is None:
            cli = self._ctx.cli
            if getattr(cli, "ip", None):
                self._ip_addr = cli.ip
            elif cli.hostname:
                self._ip_addr = _lookup_hostname(cli.hostname)
            else:
                raise ValueError("can not determine node ip")
        return self._ip_addr

    @property
    def identity(self) -> str:
        # this could be extended to use something like /etc/machine-id
        # or whatever in the future.
        if self.hostname:
            return self.hostname
        elif self.node_number:
            return f"node-{self.node_number}"
        else:
            # the dashes make this an invalid dns name
            return "-unknown-"

    @property
    def cluster_meta_uri(self) -> str:
        """Return a cluster meta uri value."""
        values = (
            # cli takes highest precedence
            self._ctx.cli.metadata_source,
            # _nodes_json should only be set if user set it using the old key
            self._nodes_json,
            # default or customized value on current key
            self._cluster_meta_uri,
        )
        for uri in values:
            if uri:
                return uri
        raise ValueError("failed to determine cluster_meta_uri")

    def _cluster_meta_init(self) -> None:
        uri = self.cluster_meta_uri
        # it'd be nice to re-use the opener infrastructure here but openers
        # don't do file modes the way we need for JSON state file or do
        # writable file types in the url_opener (urllib wrapper). For now, just
        # manually handle the string.
        if rados_opener.is_rados_uri(uri):
            self._cluster_meta_obj = (
                rados_opener.ClusterMetaRADOSObject.create_from_uri(uri)
            )
            self._waiter_obj = Sleeper()
            return
        if uri.startswith("file:"):
            path = uri.split(":", 1)[-1]
        else:
            path = uri
        if path.startswith("/"):
            path = "/" + path.rstrip("/")  # ensure one leading /
        self._cluster_meta_obj = jfile.ClusterMetaJSONFile(path)
        self._waiter_obj = best_waiter(path)

    def cluster_meta(self) -> ctdb.ClusterMeta:
        if self._cluster_meta_obj is None:
            self._cluster_meta_init()
        assert self._cluster_meta_obj is not None
        return self._cluster_meta_obj

    def cluster_meta_waiter(self) -> Waiter:
        if self._waiter_obj is None:
            self._cluster_meta_init()
        assert self._waiter_obj is not None
        return self._waiter_obj


@commands.command(name="ctdb-migrate", arg_func=_ctdb_migrate_args)
def ctdb_migrate(ctx: Context) -> None:
    """Migrate standard samba databases to CTDB databases."""
    _ctdb_ok()
    ctdb.migrate_tdb(ctx.instance_config, ctx.cli.dest_dir)
    if ctx.cli.archive:
        ctdb.archive_tdb(ctx.instance_config, ctx.cli.archive)


def _lookup_hostname(hostname: str) -> str:
    try:
        addrinfo = socket.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        ipv6_address = None

        for entry in addrinfo:
            family, _, _, _, sockaddr = entry
            ip_address = sockaddr[0]

            if ip_address.startswith("127.") or ip_address == "::1":
                continue

            if family == socket.AF_INET:
                return ip_address

            if family == socket.AF_INET6 and ipv6_address is None:
                ipv6_address = ip_address

        if ipv6_address:
            return ipv6_address

        raise RuntimeError(
            f"No valid IP address found for hostname '{hostname}'."
        )

    except socket.gaierror as e:
        _logger.error(f"Failed to resolve hostname '{hostname}': {e}")
        raise


@commands.command(name="ctdb-set-node", arg_func=_ctdb_set_node_args)
def ctdb_set_node(ctx: Context) -> None:
    """Set up the current node in the ctdb and sambacc nodes files."""
    _ctdb_ok()
    np = NodeParams(ctx)
    expected_pnn = np.node_number

    try:
        ctdb.refresh_node_in_cluster_meta(
            cmeta=np.cluster_meta(),
            identity=np.identity,
            node=np.node_ip_addr,
            pnn=int(expected_pnn or 0),
        )
        return
    except ctdb.NodeNotPresent:
        pass

    ctdb.add_node_to_cluster_meta(
        cmeta=np.cluster_meta(),
        identity=np.identity,
        node=np.node_ip_addr,
        pnn=int(expected_pnn or 0),
        in_nodes=(expected_pnn == 0),
    )
    if expected_pnn == 0:
        ctdb.ensure_ctdb_node_present(
            node=np.node_ip_addr,
            expected_pnn=expected_pnn,
            real_path=np.persistent_path,
        )


@commands.command(name="ctdb-manage-nodes", arg_func=_ctdb_general_node_args)
def ctdb_manage_nodes(ctx: Context) -> None:
    """Run a long lived process to manage the cluster metadata. It can add new
    nodes. When a new node is found, if the current node is in the correct
    state, this node will add it to CTDB.
    """
    _ctdb_ok()
    np = NodeParams(ctx)
    expected_pnn = np.node_number or 0
    waiter = np.cluster_meta_waiter()

    limiter = ErrorLimiter("ctdb_manage_nodes", 10, pause_func=waiter.wait)
    while True:
        with limiter.catch():
            ctdb.manage_cluster_meta_updates(
                cmeta=np.cluster_meta(),
                pnn=expected_pnn,
                real_path=np.persistent_path,
                pause_func=waiter.wait,
            )


def _ctdb_monitor_nodes_args(parser: argparse.ArgumentParser) -> None:
    _ctdb_must_have_node_args(parser)
    parser.add_argument(
        "--reload",
        choices=("leader", "never", "all"),
        default="leader",
        help="Specify which nodes can command CTDB to reload nodes",
    )


@commands.command(name="ctdb-monitor-nodes", arg_func=_ctdb_monitor_nodes_args)
def ctdb_monitor_nodes(ctx: Context) -> None:
    """Run a long lived process to monitor the cluster metadata.
    Unlike ctdb_manage_nodes this function assumes that the node state
    file is externally managed and primarily exists to reflect any changes
    to the cluster meta into CTDB.
    """
    _ctdb_ok()
    np = NodeParams(ctx)
    waiter = np.cluster_meta_waiter()
    leader_locator = None
    if ctx.cli.reload == "leader":
        leader_locator = best_leader_locator(ctx.instance_config)
    reload_all = ctx.cli.reload == "all"
    nodes_file_path = np.persistent_path if ctx.cli.write_nodes else None

    _logger.info("monitoring cluster meta changes")
    _logger.debug(
        "reload_all=%s leader_locator=%r", reload_all, leader_locator
    )
    limiter = ErrorLimiter("ctdb_monitor_nodes", 10, pause_func=waiter.wait)
    while True:
        with limiter.catch():
            ctdb.monitor_cluster_meta_changes(
                cmeta=np.cluster_meta(),
                pause_func=waiter.wait,
                nodes_file_path=nodes_file_path,
                leader_locator=leader_locator,
                reload_all=reload_all,
            )


def _ctdb_must_have_node_args(parser: argparse.ArgumentParser) -> None:
    _ctdb_general_node_args(parser)
    parser.add_argument(
        "--write-nodes",
        action="store_true",
        help="Write ctdb nodes file based on cluster meta contents",
    )


@commands.command(
    name="ctdb-must-have-node", arg_func=_ctdb_must_have_node_args
)
def ctdb_must_have_node(ctx: Context) -> None:
    """Block until the current node is present in the ctdb nodes file."""
    _ctdb_ok()
    np = NodeParams(ctx)
    expected_pnn = np.node_number or 0
    waiter = np.cluster_meta_waiter()

    limiter = ErrorLimiter("ctdb_must_have_node", 10, pause_func=waiter.wait)
    while True:
        with limiter.catch():
            if ctdb.pnn_in_cluster_meta(
                cmeta=np.cluster_meta(),
                pnn=expected_pnn,
            ):
                break
            _logger.info("node not yet ready")
            waiter.wait()
    if ctx.cli.write_nodes:
        _logger.info("Writing nodes file")
        ctdb.cluster_meta_to_nodes(np.cluster_meta(), dest=np.persistent_path)


def _ctdb_rados_mutex_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cluster-name",
        default="ceph",
        help="Cluster name to pass to mutex lock helper",
    )
    parser.add_argument(
        "mutex_uri",
        help="RADOS (pesudo) URI value for the object to use as a mutex",
    )


@commands.command(name="ctdb-rados-mutex", arg_func=_ctdb_rados_mutex_args)
def ctdb_rados_mutex(ctx: Context) -> None:
    """A command to wrap the rados ctdb_mutex_ceph_rados_helper and wrap
    & translate the container's ceph configuration into something
    the helper can understand.
    N.B. Another reason for this command is that ctdb requires the
    `cluster lock` value to be the same on all nodes.
    """
    if not rados_opener.is_rados_uri(ctx.cli.mutex_uri):
        raise ValueError(f"{ctx.cli.mutex_uri} is not a valid RADOS URI value")
    rinfo = rados_opener.parse_rados_uri(ctx.cli.mutex_uri)
    if rinfo["subtype"] != "object":
        raise ValueError(
            f"{ctx.cli.mutex_uri} is not a RADOS object URI value"
        )
    pool, namespace, objname = rinfo["pool"], rinfo["ns"], rinfo["key"]
    entity = ctx.cli.ceph_id["client_name"]
    if not entity:
        raise ValueError("a ceph authentication entity name is required")
    if not ctx.cli.ceph_id["full_name"]:
        entity = f"client.{entity}"
    # required arguments
    cmd = samba_cmds.ctdb_mutex_ceph_rados_helper[
        ctx.cli.cluster_name, entity, pool, objname  # cephx entity
    ]
    # optional namespace argument
    if namespace:
        cmd = cmd["-n", namespace]
    _logger.debug("executing command: %r", cmd)
    samba_cmds.execute(cmd)  # replaces process


@commands.command(name="ctdb-list-nodes", arg_func=_ctdb_general_node_args)
def ctdb_list_nodes(ctx: Context) -> None:
    """Write nodes content to stdout based on current cluster meta."""
    _ctdb_ok()
    np = NodeParams(ctx)

    ctdb.cluster_meta_to_nodes(np.cluster_meta(), sys.stdout)


class ErrorLimiter:
    def __init__(
        self,
        name: str,
        limit: int,
        *,
        pause_func: typing.Optional[typing.Callable] = None,
    ) -> None:
        self.name = name
        self.limit = limit
        self.errors = 0
        self.pause_func = pause_func

    def post_catch(self):
        if self.pause_func is not None:
            self.pause_func()

    @contextlib.contextmanager
    def catch(self) -> typing.Iterator[None]:
        try:
            _logger.debug(
                "error limiter proceeding: %s: errors=%r",
                self.name,
                self.errors,
            )
            yield
        except KeyboardInterrupt:
            raise
        except Exception as err:
            _logger.error(
                f"error during {self.name}: {err}, count={self.errors}",
                exc_info=True,
            )
            self.errors += 1
            if self.errors > self.limit:
                _logger.error(f"too many retries ({self.errors}). giving up")
                raise
            self.post_catch()
