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
import typing

from sambacc import config
from sambacc import jfile
from sambacc import samba_cmds
from sambacc.netcmd_loader import template_config
from sambacc.typelets import ExcType, ExcValue, ExcTraceback

_logger = logging.getLogger(__name__)


DB_DIR = "/var/lib/ctdb/persistent"
ETC_DIR = "/etc/ctdb"
SHARE_DIR = "/usr/share/ctdb"

CTDB_CONF: str = "/etc/ctdb/ctdb.conf"
CTDB_NODES: str = "/etc/ctdb/nodes"


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

    def _write_param(fh: typing.IO, name: str, key: str) -> None:
        value = ctdb_params.get(key)
        if value is None:
            return
        fh.write(enc(f"{name} = {value}\n"))

    fh.write(enc("[logging]\n"))
    _write_param(fh, "log level", "log_level")
    fh.write(enc("\n"))
    fh.write(enc("[cluster]\n"))
    _write_param(fh, "recovery lock", "recovery_lock")
    fh.write(enc("\n"))
    fh.write(enc("[legacy]\n"))
    _write_param(fh, "realtime scheduling", "realtime_scheduling")
    _write_param(fh, "script log level", "script_log_level")
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
    with jfile.open(path, jfile.OPEN_RW) as fh:
        jfile.flock(fh)
        data = jfile.load(fh, {})
        _update_statefile(data, identity, node, pnn, in_nodes=in_nodes)
        jfile.dump(data, fh)


def refresh_node_in_statefile(
    identity: str, node: str, pnn: int, path: str
) -> None:
    """Assuming the node is already in the statefile, update the state in
    the case that the node (IP) has changed.
    """
    with jfile.open(path, jfile.OPEN_RW) as fh:
        jfile.flock(fh)
        data = jfile.load(fh, {})
        _refresh_statefile(data, identity, node, pnn)
        jfile.dump(data, fh)


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
    with jfile.open(nodes_json, jfile.OPEN_RO) as fh:
        jfile.flock(fh)
        json_data = jfile.load(fh, {})
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
    while True:
        _logger.info("checking if node is able to make updates")
        if _node_check(pnn, nodes_json, real_path):
            _logger.info("checking for node updates")
            if _node_update(nodes_json, real_path):
                _logger.info("updated nodes")
        else:
            _logger.warning("node can not make updates")
        pause_func()


def _node_check(pnn: int, nodes_json: str, real_path: str) -> bool:
    with jfile.open(nodes_json, jfile.OPEN_RO) as fh:
        jfile.flock(fh)
        desired = jfile.load(fh, {}).get("nodes", [])
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
    json_data: dict[str, typing.Any], nodes_json: str, real_path: str
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


def _node_update(nodes_json: str, real_path: str) -> bool:
    # open r/o so that we don't initailly open for write.  we do a probe and
    # decide if anything needs to be updated if we are wrong, its not a
    # problem, we'll "time out" and reprobe later
    with jfile.open(nodes_json, jfile.OPEN_RO) as fh:
        jfile.flock(fh)
        json_data = jfile.load(fh, {})
        _, test_chg_nodes, test_need_reload = _node_update_check(
            json_data, nodes_json, real_path
        )
        if not test_chg_nodes and not test_need_reload:
            _logger.info("examined nodes state - no changes")
            return False
    # we probably need to make a change. but we recheck our state again
    # under lock, with the data file open r/w
    # update the nodes file and make changes to ctdb
    with jfile.open(nodes_json, jfile.OPEN_RW) as fh:
        jfile.flock(fh)
        json_data = jfile.load(fh, {})
        ctdb_nodes, chg_nodes, need_reload = _node_update_check(
            json_data, nodes_json, real_path
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
        with open(real_path, "w") as nffh:
            write_nodes_file(nffh, new_ctdb_nodes)
            nffh.flush()
            os.fsync(nffh)
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
        jfile.dump(json_data, fh)
        fh.flush()
        os.fsync(fh)
    return True


def ensure_ctdbd_etc_files(
    etc_path: str = ETC_DIR, src_path: str = SHARE_DIR
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


def check_nodestatus(cmd: samba_cmds.SambaCommand = samba_cmds.ctdb) -> None:
    cmd_ctdb_check = cmd["nodestatus"]
    samba_cmds.execute(cmd_ctdb_check)


class CLILeaderStatus:
    _isleader = False

    def is_leader(self) -> bool:
        return self._isleader


class CLILeaderLocator:
    """A leader locator that relies entirely on checking the
    recovery master using the ctdb command line tool.
    """

    def __enter__(self) -> CLILeaderStatus:
        mypnn = recmaster = ""
        # mypnn = <ctdb pnn>
        pnn_cmd = samba_cmds.ctdb["pnn"]
        try:
            out = subprocess.check_output(list(pnn_cmd))
            mypnn = out.decode("utf8").strip()
        except subprocess.CalledProcessError as err:
            _logger.error(f"command {pnn_cmd!r} failed: {err!r}")
        except FileNotFoundError:
            _logger.error(f"ctdb command ({pnn_cmd!r}) not found")
        # recmaster = <ctdb recmaster|leader>
        admin_cmd = samba_cmds.ctdb_leader_admin_cmd()
        recmaster_cmd = samba_cmds.ctdb[admin_cmd]
        try:
            out = subprocess.check_output(list(recmaster_cmd))
            recmaster = out.decode("utf8").strip()
        except subprocess.CalledProcessError as err:
            _logger.error(f"command {recmaster_cmd!r} failed: {err!r}")
        except FileNotFoundError:
            _logger.error(f"ctdb command ({recmaster_cmd!r}) not found")

        sts = CLILeaderStatus()
        sts._isleader = bool(mypnn) and mypnn == recmaster
        return sts

    def __exit__(
        self, exc_type: ExcType, exc_val: ExcValue, exc_tb: ExcTraceback
    ) -> bool:
        return True
