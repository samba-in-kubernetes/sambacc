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

import enum
import logging
import os
import subprocess
import time
import typing

from sambacc import config
from sambacc import leader
from sambacc import samba_cmds
from sambacc.jfile import ClusterMetaJSONFile
from sambacc.netcmd_loader import template_config
from sambacc.typelets import ExcType, ExcValue, ExcTraceback

_logger = logging.getLogger(__name__)


DB_DIR = "/var/lib/ctdb/persistent"
ETC_DIR = "/etc/ctdb"
SHARE_DIR = "/usr/share/ctdb"

CTDB_CONF: str = "/etc/ctdb/ctdb.conf"
CTDB_NODES: str = "/etc/ctdb/nodes"


class ClusterMetaObject(typing.Protocol):
    "A Cluster Meta Object can load or dump persistent cluster descriptions."

    def load(self) -> typing.Any:
        """Load a JSON-compatible object."""
        ...  # pragma: no cover

    def dump(self, data: typing.Any) -> None:
        """Dump (save) a JSON-compatible object."""
        ...  # pragma: no cover


class ClusterMeta(typing.Protocol):
    """ClusterMeta manages access to persistent cluster descriptions."""

    def open(
        self, *, read: bool = True, write: bool = False, locked: bool = False
    ) -> typing.ContextManager[ClusterMetaObject]:
        """Return a context manager with access to a cluster meta object."""
        ...  # pragma: no cover


class NodeState(str, enum.Enum):
    NEW = "new"
    READY = "ready"
    CHANGED = "changed"
    REPLACED = "replaced"
    GONE = "gone"  # reserved


def next_state(state: NodeState) -> NodeState:
    if state == NodeState.NEW:
        return NodeState.READY
    elif state == NodeState.CHANGED:
        return NodeState.REPLACED
    elif state == NodeState.REPLACED:
        return NodeState.READY
    return state


class NodeNotPresent(KeyError):
    def __init__(
        self,
        identity: typing.Any,
        pnn: typing.Optional[typing.Union[str, int]] = None,
    ) -> None:
        super().__init__(identity)
        self.identity = identity
        self.pnn = pnn


def ensure_smb_conf(
    iconfig: config.InstanceConfig, path: str = config.SMB_CONF
) -> None:
    """Ensure that the smb.conf on disk is ctdb and registry enabled."""
    with open(path, "w") as fh:
        write_smb_conf(fh, iconfig)


def write_smb_conf(fh: typing.IO, iconfig: config.InstanceConfig) -> None:
    """Write an smb.conf style output enabling ctdb and samba registry."""
    template_config(fh, iconfig.ctdb_smb_config())


def ensure_ctdb_conf(
    iconfig: config.InstanceConfig, path: str = CTDB_CONF
) -> None:
    """Ensure that the ctdb.conf on disk matches our desired state."""
    with open(path, "w") as fh:
        write_ctdb_conf(fh, iconfig.ctdb_config())


def write_ctdb_conf(
    fh: typing.IO, ctdb_params: dict, enc: typing.Callable = str
) -> None:
    """Write a ctdb.conf style output."""

    def _write_param(name: str, key: str) -> None:
        value = ctdb_params.get(key)
        if value is None:
            return
        fh.write(enc(f"{name} = {value}\n"))

    fh.write(enc("[logging]\n"))
    _write_param("log level", "log_level")
    fh.write(enc("\n"))
    fh.write(enc("[cluster]\n"))
    _write_param("recovery lock", "recovery_lock")
    if ctdb_params.get("nodes_cmd"):
        nodes_cmd = ctdb_params["nodes_cmd"]
        fh.write(enc(f"nodes list = !{nodes_cmd}"))
    fh.write(enc("\n"))
    fh.write(enc("[legacy]\n"))
    _write_param("realtime scheduling", "realtime_scheduling")
    _write_param("script log level", "script_log_level")
    fh.write(enc("\n"))


def ensure_ctdb_nodes(
    ctdb_nodes: list[str], real_path: str, canon_path: str = CTDB_NODES
) -> None:
    """Ensure a real nodes file exists, containing the specificed content,
    and has a symlink in the proper place for ctdb.
    """
    try:
        os.unlink(canon_path)
    except FileNotFoundError:
        pass
    os.symlink(real_path, canon_path)
    # XXX: add locking?
    with open(real_path, "w") as fh:
        write_nodes_file(fh, ctdb_nodes)


def write_nodes_file(
    fh: typing.IO, ctdb_nodes: list[str], enc: typing.Callable = str
) -> None:
    """Write the ctdb nodes file."""
    for node in ctdb_nodes:
        fh.write(enc(f"{node}\n"))


def read_nodes_file(fh: typing.IO) -> list[str]:
    """Read content from an open ctdb nodes file."""
    entries = []
    for line in fh:
        entries.append(line.strip())
    return entries


def read_ctdb_nodes(path: str = CTDB_NODES) -> list[str]:
    """Read the content of the ctdb nodes file."""
    try:
        with open(path, "r") as fh:
            entries = read_nodes_file(fh)
    except FileNotFoundError:
        return []
    return entries


class PublicAddrAssignment(typing.TypedDict):
    address: str
    interfaces: list[str]


def _ensure_public_addresses_file(
    path: str, addrs: list[PublicAddrAssignment]
) -> None:
    with open(path, "w") as fh:
        _write_public_addresses_file(fh, addrs)


def _write_public_addresses_file(
    fh: typing.IO, addrs: list[PublicAddrAssignment]
) -> None:
    for entry in addrs:
        fh.write(entry["address"])
        if entry["interfaces"]:
            ifaces = ",".join(entry["interfaces"])
            fh.write(f" {ifaces}")
        fh.write("\n")


def ensure_ctdb_node_present(
    node: str,
    real_path: str,
    canon_path: str = CTDB_NODES,
    expected_pnn: typing.Optional[int] = None,
) -> None:
    """Ensure that the ctdb nodes file is populated with at least the
    node given. The optional `expect_pnn` can be provided to ensure that
    the node occupies the correct position in the nodes file.
    """
    nodes = read_ctdb_nodes(real_path)
    if node not in nodes:
        nodes.append(node)
    if expected_pnn is not None:
        try:
            found_pnn = nodes.index(node)
        except ValueError:
            found_pnn = -1
        if expected_pnn != found_pnn:
            raise ValueError(f"expected pnn {expected_pnn} is not {found_pnn}")
    ensure_ctdb_nodes(nodes, real_path=real_path, canon_path=canon_path)


def add_node_to_statefile(
    identity: str, node: str, pnn: int, path: str, in_nodes: bool = False
) -> None:
    """Add the given node's identity, (node) IP, and PNN to the JSON based
    state file, located at `path`. If in_nodes is true, the state file will
    reflect that the node is already added to the CTDB nodes file.
    """
    add_node_to_cluster_meta(
        ClusterMetaJSONFile(path), identity, node, pnn, in_nodes=in_nodes
    )


def add_node_to_cluster_meta(
    cmeta: ClusterMeta,
    identity: str,
    node: str,
    pnn: int,
    in_nodes: bool = False,
) -> None:
    """Add the given node's identity, (node) IP, and PNN to the cluster
    metadata.  If in_nodes is true, the state file will reflect that the node
    is already added to the CTDB nodes file.
    """
    with cmeta.open(write=True, locked=True) as cmo:
        data = cmo.load()
        _update_statefile(data, identity, node, pnn, in_nodes=in_nodes)
        cmo.dump(data)


def refresh_node_in_statefile(
    identity: str, node: str, pnn: int, path: str
) -> None:
    """Assuming the node is already in the statefile, update the state in
    the case that the node (IP) has changed.
    """
    refresh_node_in_cluster_meta(
        ClusterMetaJSONFile(path), identity, node, pnn
    )


def refresh_node_in_cluster_meta(
    cmeta: ClusterMeta, identity: str, node: str, pnn: int
) -> None:
    """Assuming the node is already in the cluster metadata, update the state
    in the case that the node (IP) has changed.
    """
    with cmeta.open(write=True, locked=True) as cmo:
        data = cmo.load()
        _refresh_statefile(data, identity, node, pnn)
        cmo.dump(data)


def _update_statefile(
    data: dict[str, typing.Any],
    identity: str,
    node: str,
    pnn: int,
    in_nodes: bool = False,
) -> None:
    data.setdefault("nodes", [])
    for entry in data["nodes"]:
        if pnn == entry["pnn"]:
            raise ValueError("duplicate pnn")
        if identity == entry["identity"]:
            raise ValueError("duplicate identity")
    state = NodeState.NEW
    if in_nodes:
        state = NodeState.READY
    data["nodes"].append(
        {
            "identity": identity,
            "node": node,
            "pnn": pnn,
            "state": state,
        }
    )


def _refresh_statefile(
    data: dict[str, typing.Any],
    identity: str,
    node: str,
    pnn: int,
    in_nodes: bool = False,
) -> None:
    data.setdefault("nodes", [])
    node_entry = None
    for entry in data["nodes"]:
        if pnn == entry["pnn"] and identity == entry["identity"]:
            node_entry = entry
            break
        if pnn == entry["pnn"]:
            raise ValueError(
                f"matching pnn ({pnn}) identity={entry['identity']}"
            )
    if not node_entry:
        raise NodeNotPresent(identity, pnn)
    if node_entry["node"] == node:
        # do nothing
        return
    node_entry["node"] = node
    node_entry["state"] = NodeState.CHANGED


def _get_state(entry: dict[str, typing.Any]) -> NodeState:
    return NodeState(entry["state"])


def _get_state_ok(entry: dict[str, typing.Any]) -> bool:
    return _get_state(entry) == NodeState.READY


def pnn_in_nodes(pnn: int, nodes_json: str, real_path: str) -> bool:
    """Returns true if the specified pnn has an entry in the nodes json
    file and that the node is already added to the ctdb nodes file.
    """
    return pnn_in_cluster_meta(ClusterMetaJSONFile(nodes_json), pnn)


def pnn_in_cluster_meta(cmeta: ClusterMeta, pnn: int) -> bool:
    """Returns true if the specified pnn has an entry in the cluster metadata
    and that entry is ready for use.
    """
    with cmeta.open(locked=True) as cmo:
        json_data = cmo.load()
    current_nodes = json_data.get("nodes", [])
    for entry in current_nodes:
        if pnn == entry["pnn"] and _get_state_ok(entry):
            return True
    return False


def manage_nodes(
    pnn: int,
    nodes_json: str,
    real_path: str,
    pause_func: typing.Callable,
) -> None:
    """Monitor nodes json for updates, reflecting those changes into ctdb."""
    manage_cluster_meta_updates(
        ClusterMetaJSONFile(nodes_json),
        pnn,
        real_path,
        pause_func,
    )


def manage_cluster_meta_updates(
    cmeta: ClusterMeta,
    pnn: int,
    real_path: str,
    pause_func: typing.Callable,
) -> None:
    """Monitor cluster meta for updates, reflecting those changes into ctdb."""
    while True:
        _logger.info("checking if node is able to make updates")
        if _node_check(cmeta, pnn, real_path):
            _logger.info("checking for node updates")
            if _node_update(cmeta, real_path):
                _logger.info("updated nodes")
        else:
            _logger.warning("node can not make updates")
        pause_func()


def _node_check(cmeta: ClusterMeta, pnn: int, real_path: str) -> bool:
    with cmeta.open(locked=True) as cmo:
        desired = cmo.load().get("nodes", [])
    ctdb_nodes = read_ctdb_nodes(real_path)
    # first: check to see if the current node is in the nodes file
    try:
        my_desired = [e for e in desired if e.get("pnn") == pnn][0]
    except IndexError:
        # no entry found for this node
        _logger.warning(f"PNN {pnn} not found in json state file")
        return False
    if my_desired["node"] not in ctdb_nodes:
        # this current node is not in the nodes file.
        # it is ineligible to make changes to the nodes file
        return False
    # this node is already in the nodes file!
    return True


def _node_update_check(
    json_data: dict[str, typing.Any], real_path: str
) -> tuple[list[str], list[typing.Any], list[typing.Any]]:
    desired = json_data.get("nodes", [])
    ctdb_nodes = read_ctdb_nodes(real_path)
    update_nodes = []
    need_reload = []
    _update_states = (NodeState.NEW, NodeState.CHANGED, NodeState.REPLACED)
    for entry in desired:
        pnn = entry["pnn"]
        matched = _node_line(ctdb_nodes, pnn) == entry["node"]
        if matched and _get_state_ok(entry):
            # everything's fine. skip this entry
            continue
        elif not matched:
            if entry["state"] in _update_states:
                update_nodes.append(entry)
                need_reload.append(entry)
            elif entry["state"] == NodeState.READY:
                msg = f"ready node (pnn {pnn}) missing from {ctdb_nodes}"
                raise ValueError(msg)
        else:
            # node present but state indicates
            # update is not finalized
            need_reload.append(entry)
    return ctdb_nodes, update_nodes, need_reload


def _node_line(ctdb_nodes: list[str], pnn: int) -> str:
    try:
        return ctdb_nodes[pnn]
    except IndexError:
        return ""


def _entry_to_node(ctdb_nodes: list[str], entry: dict[str, typing.Any]) -> str:
    pnn: int = entry["pnn"]
    if entry["state"] == NodeState.CHANGED:
        return "#{}".format(ctdb_nodes[pnn].strip("#"))
    return entry["node"]


def _node_update(cmeta: ClusterMeta, real_path: str) -> bool:
    # open r/o so that we don't initailly open for write.  we do a probe and
    # decide if anything needs to be updated if we are wrong, its not a
    # problem, we'll "time out" and reprobe later
    with cmeta.open(locked=True) as cmo:
        json_data = cmo.load()
        _, test_chg_nodes, test_need_reload = _node_update_check(
            json_data, real_path
        )
        if not test_chg_nodes and not test_need_reload:
            _logger.info("examined nodes state - no changes")
            return False
    # we probably need to make a change. but we recheck our state again
    # under lock, with the data file open r/w
    # update the nodes file and make changes to ctdb
    with cmeta.open(write=True, locked=True) as cmo:
        json_data = cmo.load()
        ctdb_nodes, chg_nodes, need_reload = _node_update_check(
            json_data, real_path
        )
        if not chg_nodes and not need_reload:
            _logger.info("reexamined nodes state - no changes")
            return False
        _logger.info("writing updates to ctdb nodes file")
        new_ctdb_nodes = list(ctdb_nodes)
        for entry in chg_nodes:
            pnn = entry["pnn"]
            expected_line = _entry_to_node(ctdb_nodes, entry)
            if _node_line(new_ctdb_nodes, pnn) == expected_line:
                continue
            if entry["state"] == NodeState.NEW:
                if pnn != len(new_ctdb_nodes):
                    raise ValueError(
                        f"unexpected pnn in new entry {entry}:"
                        " nodes: {new_ctdb_nodes}"
                    )
                new_ctdb_nodes.append(expected_line)
            else:
                new_ctdb_nodes[pnn] = expected_line
        _save_nodes(real_path, new_ctdb_nodes)
        _logger.info("running: ctdb reloadnodes")
        subprocess.check_call(list(samba_cmds.ctdb["reloadnodes"]))
        for entry in need_reload:
            entry["state"] = next_state(entry["state"])
            _logger.debug(
                "setting node identity=[{}] pnn={} to {}".format(
                    entry["identity"],
                    entry["pnn"],
                    entry["state"],
                )
            )
        cmo.dump(json_data)
    return True


def cluster_meta_to_nodes(
    cmeta: ClusterMeta, dest: typing.Union[str, typing.IO]
) -> None:
    """Write a nodes file based on the current content of the cluster
    metadata."""
    with cmeta.open(locked=True) as cmo:
        json_data = cmo.load()
        nodes = json_data.get("nodes", [])
        _logger.info("Found node metadata: %r", nodes)
        ctdb_nodes = _cluster_meta_to_ctdb_nodes(nodes)
        if isinstance(dest, str):
            _logger.info("Will write nodes: %s", ctdb_nodes)
            _save_nodes(dest, ctdb_nodes)
        else:
            write_nodes_file(dest, ctdb_nodes)


def _cluster_meta_to_ctdb_nodes(nodes: list[dict]) -> list[str]:
    pnn_max = max(n["pnn"] for n in nodes) + 1  # pnn is zero indexed
    ctdb_nodes: list[str] = [""] * pnn_max
    for entry in nodes:
        pnn = entry["pnn"]
        # overwrite the pnn indexed entry with expected value
        ctdb_nodes[pnn] = _entry_to_node(ctdb_nodes, entry)
    return ctdb_nodes


def _save_nodes(path: str, ctdb_nodes: list[str]) -> None:
    with open(path, "w") as nffh:
        write_nodes_file(nffh, ctdb_nodes)
        nffh.flush()
        os.fsync(nffh)


def monitor_cluster_meta_changes(
    cmeta: ClusterMeta,
    pause_func: typing.Callable,
    *,
    nodes_file_path: typing.Optional[str] = None,
    reload_all: bool = False,
    leader_locator: typing.Optional[leader.LeaderLocator] = None,
) -> None:
    """Monitor cluster meta for changes, reflecting those changes into ctdb.

    Unlike manage_cluster_meta_updates this function never changes the
    contents of the nodes list in the cluster meta and takes those values
    as a given, assuming some external agent has the correct global view of
    the cluster and is updating it correctly. This function exists to
    translate that content into something ctdb can understand.
    """
    prev_meta: dict[str, typing.Any] = {}
    if nodes_file_path:
        prev_nodes = read_ctdb_nodes(nodes_file_path)
    else:
        with cmeta.open(locked=True) as cmo:
            meta1 = cmo.load()
        prev_nodes = _cluster_meta_to_ctdb_nodes(meta1.get("nodes", []))
    _logger.debug("initial cluster meta content: %r", prev_meta)
    _logger.debug("initial nodes content: %r", prev_nodes)
    while True:
        pause_func()
        with cmeta.open(locked=True) as cmo:
            curr_meta = cmo.load()
        if curr_meta == prev_meta:
            _logger.debug("cluster meta content unchanged: %r", curr_meta)
            continue
        if len(prev_meta) > 0 and len(curr_meta) == 0:
            # cluster is possibly (probably?) being destroyed.
            # Return from this loop and let the command-level loop decide if
            # this function needs to be restarted or not. There's a chance this
            # process will be terminated very soon anyway.
            _logger.warning("no current nodes available")
            return
        _logger.info("cluster meta content changed")
        _logger.debug(
            "cluster meta: previous=%r current=%r", prev_meta, curr_meta
        )
        prev_meta = curr_meta

        # maybe some other metadata changed?
        expected_nodes = _cluster_meta_to_ctdb_nodes(
            curr_meta.get("nodes", [])
        )
        if prev_nodes == expected_nodes:
            _logger.debug("ctdb nodes list unchanged: %r", expected_nodes)
            continue
        _logger.info("ctdb nodes list changed")
        _logger.debug(
            "nodes list: previous=%r current=%r", prev_nodes, expected_nodes
        )
        prev_nodes = expected_nodes

        if nodes_file_path:
            _logger.info("updating nodes file: %s", nodes_file_path)
            _save_nodes(nodes_file_path, expected_nodes)
        _maybe_reload_nodes_retry(leader_locator, reload_all=reload_all)


def _maybe_reload_nodes_retry(
    leader_locator: typing.Optional[leader.LeaderLocator] = None,
    reload_all: bool = False,
    *,
    tries: int = 5,
) -> None:
    for idx in range(tries):
        time.sleep(1 << idx)
        try:
            _maybe_reload_nodes(leader_locator, reload_all=reload_all)
            return
        except subprocess.CalledProcessError:
            _logger.exception("failed to execute reload nodes command")
    raise RuntimeError("exceeded retries running reload nodes command")


def _maybe_reload_nodes(
    leader_locator: typing.Optional[leader.LeaderLocator] = None,
    reload_all: bool = False,
) -> None:
    """Issue a reloadnodes command if leader_locator is available and
    node is leader or reload_all is true.
    """
    if reload_all:
        _logger.info("running: ctdb reloadnodes")
        subprocess.check_call(list(samba_cmds.ctdb["reloadnodes"]))
        return
    if leader_locator is None:
        _logger.warning("no leader locator: not calling reloadnodes")
        return
    # use the leader locator to only issue the reloadnodes command once
    # for a change instead of all the nodes "spamming" the cluster
    with leader_locator as ll:
        if ll.is_leader():
            _logger.info("running: ctdb reloadnodes")
            subprocess.check_call(list(samba_cmds.ctdb["reloadnodes"]))
        else:
            _logger.info("node is not leader. skipping reloadnodes")


def ensure_ctdbd_etc_files(
    etc_path: str = ETC_DIR,
    src_path: str = SHARE_DIR,
    *,
    iconfig: typing.Optional[config.InstanceConfig] = None,
) -> None:
    """Ensure certain files that ctdbd expects to exist in its etc dir
    do exist.
    """
    functions_src = os.path.join(src_path, "functions")
    functions_dst = os.path.join(etc_path, "functions")
    notify_src = os.path.join(src_path, "notify.sh")
    notify_dst = os.path.join(etc_path, "notify.sh")
    legacy_scripts_src = os.path.join(src_path, "events/legacy")
    legacy_scripts_dst = os.path.join(etc_path, "events/legacy")
    link_legacy_scripts = ["00.ctdb.script"]

    public_addresses: list[PublicAddrAssignment] = []
    if iconfig:
        ctdb_conf = iconfig.ctdb_config()
        # todo: when we have a real config object for ctdb conf we can drop
        # the typing.cast
        public_addresses = typing.cast(
            list[PublicAddrAssignment], ctdb_conf.get("public_addresses", [])
        )
    if public_addresses:
        link_legacy_scripts.append("10.interface.script")

    os.makedirs(etc_path, exist_ok=True)
    try:
        os.unlink(functions_dst)
    except FileNotFoundError:
        pass
    os.symlink(functions_src, functions_dst)

    try:
        os.unlink(notify_dst)
    except FileNotFoundError:
        pass
    os.symlink(notify_src, notify_dst)

    os.makedirs(legacy_scripts_dst, exist_ok=True)
    for legacy_script_name in link_legacy_scripts:
        lscript_src = os.path.join(legacy_scripts_src, legacy_script_name)
        lscript_dst = os.path.join(legacy_scripts_dst, legacy_script_name)
        try:
            os.unlink(lscript_dst)
        except FileNotFoundError:
            pass
        os.symlink(lscript_src, lscript_dst)

    if public_addresses:
        pa_path = os.path.join(etc_path, "public_addresses")
        _ensure_public_addresses_file(pa_path, public_addresses)


_SRC_TDB_FILES = [
    "account_policy.tdb",
    "group_mapping.tdb",
    "passdb.tdb",
    "registry.tdb",
    "secrets.tdb",
    "share_info.td",
    "winbindd_idmap.tdb",
]

_SRC_TDB_DIRS = [
    "/var/lib/samba",
    "/var/lib/samba/private",
]


def migrate_tdb(
    iconfig: config.InstanceConfig, dest_dir: str, pnn: int = 0
) -> None:
    """Migrate TDB files into CTDB."""
    # TODO: these paths should be based on our instance config, not hard coded
    for tdbfile in _SRC_TDB_FILES:
        for parent in _SRC_TDB_DIRS:
            tdb_path = os.path.join(parent, tdbfile)
            if _has_tdb_file(tdb_path):
                _convert_tdb_file(tdb_path, dest_dir, pnn=pnn)


def _has_tdb_file(tdb_path: str) -> bool:
    # TODO: It would be preferable to handle errors from the convert
    # function only, but it if ltdbtool is missing it raises FileNotFoundError
    # and its not simple to disambiguate between the command missing and the
    # tdb file missing.
    _logger.info(f"Checking for {tdb_path}")
    return os.path.isfile(tdb_path)


def _convert_tdb_file(tdb_path: str, dest_dir: str, pnn: int = 0) -> None:
    orig_name = os.path.basename(tdb_path)
    opath = os.path.join(dest_dir, f"{orig_name}.{pnn}")
    _logger.info(f"Converting {tdb_path} to {opath} ...")
    cmd = samba_cmds.ltdbtool["convert", "-s0", tdb_path, opath]
    subprocess.check_call(list(cmd))


def archive_tdb(iconfig: config.InstanceConfig, dest_dir: str) -> None:
    """Arhive TDB files into a given directory."""
    # TODO: these paths should be based on our instance config, not hard coded
    try:
        os.mkdir(dest_dir)
        _logger.debug("dest_dir: %r created", dest_dir)
    except FileExistsError:
        _logger.debug("dest_dir: %r already exists", dest_dir)
    for tdbfile in _SRC_TDB_FILES:
        for parent in _SRC_TDB_DIRS:
            tdb_path = os.path.join(parent, tdbfile)
            if _has_tdb_file(tdb_path):
                dest_path = os.path.join(dest_dir, tdbfile)
                _logger.info("archiving: %r -> %r", tdb_path, dest_path)
                os.rename(tdb_path, dest_path)


def check_nodestatus(cmd: samba_cmds.SambaCommand = samba_cmds.ctdb) -> None:
    cmd_ctdb_check = cmd["nodestatus"]
    samba_cmds.execute(cmd_ctdb_check)


def _read_command_pnn(cmd: samba_cmds.SambaCommand) -> typing.Optional[int]:
    """Run a ctdb command assuming it returns a pnn value. Return the pnn as an
    int on success, None on command failure.
    """
    try:
        out = subprocess.check_output(list(cmd))
        pnntxt = out.decode("utf8").strip()
    except subprocess.CalledProcessError as err:
        _logger.error(f"command {cmd!r} failed: {err!r}")
        return None
    except FileNotFoundError:
        _logger.error(f"ctdb command ({cmd!r}) not found")
        return None
    try:
        return int(pnntxt)
    except ValueError:
        _logger.debug(f"ctdb command wrote invalid pnn: {pnntxt!r}")
        return None


def current_pnn() -> typing.Optional[int]:
    """Run the `ctdb pnn` command. Returns the pnn value or None if the command
    fails.
    """
    return _read_command_pnn(samba_cmds.ctdb["pnn"])


def leader_pnn() -> typing.Optional[int]:
    """Run the `ctdb leader` (or equivalent) command. Returns the pnn value or
    None if the command fails.
    """
    # recmaster command: <ctdb recmaster|leader>
    admin_cmd = samba_cmds.ctdb_leader_admin_cmd()
    return _read_command_pnn(samba_cmds.ctdb[admin_cmd])


class CLILeaderStatus:
    _isleader = False

    def is_leader(self) -> bool:
        return self._isleader


class CLILeaderLocator:
    """A leader locator that relies entirely on checking the
    recovery master using the ctdb command line tool.
    """

    def __enter__(self) -> CLILeaderStatus:
        mypnn = current_pnn()
        leader = leader_pnn()
        sts = CLILeaderStatus()
        sts._isleader = mypnn is not None and mypnn == leader
        return sts

    def __exit__(
        self, exc_type: ExcType, exc_val: ExcValue, exc_tb: ExcTraceback
    ) -> bool:
        return True
