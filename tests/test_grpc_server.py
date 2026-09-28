#
# sambacc: a samba container configuration tool
# Copyright (C) 2025  John Mulligan
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

import collections

import pytest

from sambacc.grpc import backend

json1 = """
{
  "timestamp": "2025-05-08T20:41:57.273489+0000",
  "version": "4.23.0pre1-UNKNOWN",
  "smb_conf": "/etc/samba/smb.conf",
  "sessions": {
    "2891148582": {
      "session_id": "2891148582",
      "server_id": {
        "pid": "1243",
        "task_id": "0",
        "vnn": "2",
        "unique_id": "1518712196307698939"
      },
      "uid": 103107,
      "gid": 102513,
      "username": "DOMAIN1\\\\bwayne",
      "groupname": "DOMAIN1\\\\domain users",
      "creation_time": "2025-05-08T20:39:36.456835+00:00",
      "expiration_time": "30828-09-14T02:48:05.477581+00:00",
      "auth_time": "2025-05-08T20:39:36.457633+00:00",
      "remote_machine": "127.0.0.1",
      "hostname": "ipv4:127.0.0.1:59396",
      "session_dialect": "SMB3_11",
      "client_guid": "adc145fe-0677-4ab6-9d61-c25b30211174",
      "encryption": {
        "cipher": "-",
        "degree": "none"
      },
      "signing": {
        "cipher": "AES-128-GMAC",
        "degree": "partial"
      },
      "channels": {
        "1": {
          "channel_id": "1",
          "creation_time": "2025-05-08T20:39:36.456835+00:00",
          "local_address": "ipv4:127.0.0.1:445",
          "remote_address": "ipv4:127.0.0.1:59396",
          "transport": "tcp"
        }
      }
    }
  },
  "tcons": {
    "3757739897": {
      "service": "cephomatic",
      "server_id": {
        "pid": "1243",
        "task_id": "0",
        "vnn": "2",
        "unique_id": "1518712196307698939"
      },
      "tcon_id": "3757739897",
      "session_id": "2891148582",
      "machine": "127.0.0.1",
      "connected_at": "2025-05-08T20:39:36.464088+00:00",
      "encryption": {
        "cipher": "-",
        "degree": "none"
      },
      "signing": {
        "cipher": "-",
        "degree": "none"
      }
    }
  },
  "open_files": {}
}
"""


def server_config(socket_path=""):
    import sambacc.grpc.config

    class TestConfig(sambacc.grpc.config.ServerConfig):
        def wait(self, server):
            self._server = server

    tc = TestConfig.default()
    tc.max_workers = 3
    tc.first_connection().address = f"unix:{socket_path}"
    tc.first_connection().insecure = True
    return tc


class MockBackend:
    def __init__(self):
        self._counter = collections.Counter()
        self._versions = backend.Versions(
            samba_version="4.99.5",
            sambacc_version="a.b.c",
            container_version="test.v",
        )
        self._is_clustered = False
        self._status = backend.Status.parse(json1)
        self._cluster_level = backend.ClusterLevelInfo.parse_showall(
            clusterlevel_showall1
        )
        self._upgrade_result = backend.ClusterLevelUpgradeResult.parse_upgrade(
            clusterlevel_upgrade_already_current
        )
        self._cluster_level_features = (
            backend.ClusterLevelFeatures.parse_features(clusterlevel_features1)
        )
        self._kaboom = None

    def get_versions(self) -> backend.Versions:
        self._counter["get_versions"] += 1
        if self._kaboom:
            raise self._kaboom
        return self._versions

    def is_clustered(self) -> bool:
        self._counter["is_clustered"] += 1
        return self._is_clustered

    def get_status(self) -> backend.Status:
        self._counter["get_status"] += 1
        return self._status

    def close_share(self, share_name: str, denied_users: bool) -> None:
        self._counter["close_share"] += 1

    def kill_client(self, ip_address: str) -> None:
        self._counter["kill_client"] += 1

    def config_dump(self, source, hash_alg):
        self._counter["config_dump"] += 1
        if self._kaboom:
            raise self._kaboom
        yield backend.DumpItem(line_number=0, content="foo\n")
        yield backend.DumpItem(line_number=0, content="bar\n")
        yield backend.DumpItem(line_number=0, content="baz\n")
        yield backend.DumpItem(line_number=0, content="bingo\n")
        if hash_alg:
            yield backend.DumpItem(
                line_number=-1, hash_type="sha256", content="xxxxxxxx"
            )

    def config_dump_digest(self, source, hash_alg):
        self._counter["config_dump_digest"] += 1
        return backend.DumpItem(
            line_number=-1, hash_type="sha256", content="xxxxxxxx"
        )

    def config_share_list(self, source):
        self._counter["config_share_list"] += 1
        yield backend.ShareEntry(name="alice")
        yield backend.ShareEntry(name="bob")
        yield backend.ShareEntry(name="zongo")

    def set_debug_level(self, server, debug_level):
        self._counter["set_debug_level"] += 1

    def get_debug_level(self, server):
        self._counter["get_debug_level"] += 1
        return "ERROR" if server is backend.ServerType.CTDB else "10"

    def get_active_cluster_level(self):
        self._counter["get_active_cluster_level"] += 1
        if self._kaboom:
            raise self._kaboom
        return self._cluster_level.active_level

    def get_cluster_level_details(self):
        self._counter["get_cluster_level_details"] += 1
        if self._kaboom:
            raise self._kaboom
        return self._cluster_level

    def upgrade_cluster_level(self, apply=False):
        self._counter["upgrade_cluster_level"] += 1
        if self._kaboom:
            raise self._kaboom
        return self._upgrade_result

    def cluster_level_features(self):
        self._counter["cluster_level_features"] += 1
        if self._kaboom:
            raise self._kaboom
        return self._cluster_level_features


@pytest.fixture()
def mock_grpc_server(tmp_path):
    try:
        import sambacc.grpc.server
    except ImportError:
        pytest.skip("can not import grpc server")

    tc = server_config(socket_path=tmp_path / "grpc.sock")
    tc.backend = MockBackend()
    tc.address = tc.first_connection().address
    sambacc.grpc.server.serve(tc, tc.backend)
    assert tc._server
    assert tc.backend
    yield tc
    tc._server.stop(0.1).wait()


def test_info(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.Info(_pb.InfoRequest())

    assert mock_grpc_server.backend._counter["get_versions"] == 1
    assert rsp.samba_info.version == "4.99.5"
    assert not rsp.samba_info.clustered
    assert rsp.container_info.sambacc_version == "a.b.c"
    assert rsp.container_info.container_version == "test.v"


def test_info_error(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._kaboom = ValueError("kaboom")
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        with pytest.raises(grpc.RpcError):
            client.Info(_pb.InfoRequest())

    assert mock_grpc_server.backend._counter["get_versions"] == 1


def test_status(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.Status(_pb.StatusRequest())

    assert mock_grpc_server.backend._counter["get_status"] == 1
    assert rsp.server_timestamp == "2025-05-08T20:41:57.273489+0000"
    # data assertions
    assert len(rsp.sessions) == 1
    assert rsp.sessions[0].session_id == "2891148582"
    assert rsp.sessions[0].uid == 103107
    assert rsp.sessions[0].gid == 102513
    assert rsp.sessions[0].username == "DOMAIN1\\bwayne"
    assert rsp.sessions[0].encryption
    assert rsp.sessions[0].encryption.cipher == ""
    assert rsp.sessions[0].encryption.degree == "none"
    assert rsp.sessions[0].signing
    assert rsp.sessions[0].signing.cipher == "AES-128-GMAC"
    assert rsp.sessions[0].signing.degree == "partial"


def test_get_active_cluster_level(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.GetActiveClusterLevel(_pb.GetActiveClusterLevelRequest())

    counter = mock_grpc_server.backend._counter
    assert counter["get_active_cluster_level"] == 1
    assert rsp.major == 1
    assert rsp.minor == 0


def test_get_cluster_level_details(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.GetClusterLevelDetails(
            _pb.GetClusterLevelDetailsRequest()
        )

    counter = mock_grpc_server.backend._counter
    assert counter["get_cluster_level_details"] == 1
    assert rsp.active_level.major == 1
    assert rsp.active_level.minor == 0
    assert len(rsp.nodes) == 3
    assert not rsp.upgrade_possible


def test_upgrade_cluster_level(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.UpgradeClusterLevel(
            _pb.UpgradeClusterLevelRequest(apply=False)
        )

    assert mock_grpc_server.backend._counter["upgrade_cluster_level"] == 1
    assert rsp.dry_run
    assert rsp.status == _pb.CLUSTER_LEVEL_UPGRADE_STATUS_ALREADY_CURRENT
    assert rsp.unknown_status == ""
    assert rsp.old_level.major == 1


def test_upgrade_cluster_level_unknown_status(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._upgrade_result = (
        backend.ClusterLevelUpgradeResult(dry_run=True, status="bogus")
    )
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.UpgradeClusterLevel(
            _pb.UpgradeClusterLevelRequest(apply=False)
        )

    assert rsp.status == _pb.CLUSTER_LEVEL_UPGRADE_STATUS_UNKNOWN
    assert rsp.unknown_status == "bogus"


def test_get_cluster_level_features(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.GetClusterLevelFeatures(_pb.ClusterLevelFeaturesRequest())

    assert mock_grpc_server.backend._counter["cluster_level_features"] == 1
    assert rsp.cluster_support
    assert rsp.ctdb_socket == "/run/samba/ctdb/ctdbd.socket"
    assert rsp.ctdb_protocol == 1
    assert len(rsp.supported_ranges) == 1


def test_close_share(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.CloseShare(_pb.CloseShareRequest(share_name="bob"))

    assert mock_grpc_server.backend._counter["close_share"] == 1
    assert rsp


def test_kill_client(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.KillClientConnection(
            _pb.KillClientRequest(ip_address="192.168.76.18")
        )

    assert mock_grpc_server.backend._counter["kill_client"] == 1
    assert rsp


def test_config_dump(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.ConfigDump(
            _pb.ConfigDumpRequest(source=_pb.CONFIG_FOR_SAMBA)
        )
        items = list(rsp)
    assert len(items) == 4
    assert [i.line.content for i in items] == [
        "foo\n",
        "bar\n",
        "baz\n",
        "bingo\n",
    ]


def test_config_dump_with_digest(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.ConfigDump(
            _pb.ConfigDumpRequest(
                source=_pb.CONFIG_FOR_SAMBA,
                hash=_pb.HASH_ALG_SHA256,
            )
        )
        items = list(rsp)
    assert len(items) == 5
    assert [i.line.content for i in items[:-1]] == [
        "foo\n",
        "bar\n",
        "baz\n",
        "bingo\n",
    ]
    assert items[-1].digest.hash == _pb.HASH_ALG_SHA256
    assert items[-1].digest.config_digest == "xxxxxxxx"


def test_config_summary(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.ConfigSummary(
            _pb.ConfigDumpRequest(
                source=_pb.CONFIG_FOR_SAMBA,
                hash=_pb.HASH_ALG_SHA256,
            )
        )
    assert rsp.digest.hash == _pb.HASH_ALG_SHA256
    assert rsp.digest.config_digest == "xxxxxxxx"


def test_config_shares_list(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        rsp = client.ConfigSharesList(
            _pb.ConfigSharesListRequest(
                source=_pb.CONFIG_FOR_SAMBA,
            )
        )
        items = list(rsp)
    assert len(items) == 3
    assert items[0].name == "alice"
    assert items[1].name == "bob"
    assert items[2].name == "zongo"


def test_config_dump_error_unimplemented(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._kaboom = NotImplementedError("samba")
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        with pytest.raises(grpc.RpcError):
            res = client.ConfigDump(
                _pb.ConfigDumpRequest(
                    source=_pb.CONFIG_FOR_SAMBA,
                    hash=_pb.HASH_ALG_SHA256,
                )
            )
            # consume stream to trigger error
            list(res)


def test_config_dump_error_not_found(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._kaboom = FileNotFoundError("ctdb")
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        with pytest.raises(grpc.RpcError):
            res = client.ConfigDump(
                _pb.ConfigDumpRequest(
                    source=_pb.CONFIG_FOR_SAMBA,
                    hash=_pb.HASH_ALG_SHA256,
                )
            )
            # consume stream to trigger error
            list(res)


def test_set_debug_level(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._kaboom = FileNotFoundError("ctdb")
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        res = client.SetDebugLevel(
            _pb.SetDebugLevelRequest(
                process=_pb.SMB_PROCESS_SMB,
                debug_level="7",
            )
        )
    assert res.process == _pb.SMB_PROCESS_SMB
    assert res.debug_level == "7"
    assert mock_grpc_server.backend._counter["set_debug_level"] == 1


def test_set_debug_level_error(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._kaboom = FileNotFoundError("ctdb")
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        with pytest.raises(grpc.RpcError):
            client.SetDebugLevel(
                _pb.SetDebugLevelRequest(
                    process=2222,  # junk value
                    debug_level="7",
                )
            )


def test_get_debug_level(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._kaboom = FileNotFoundError("ctdb")
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        res = client.GetDebugLevel(
            _pb.GetDebugLevelRequest(
                process=_pb.SMB_PROCESS_SMB,
            )
        )
    assert res.process == _pb.SMB_PROCESS_SMB
    assert res.debug_level == "10"
    assert mock_grpc_server.backend._counter["get_debug_level"] == 1


def test_get_debug_level_ctdb(mock_grpc_server):
    import grpc
    import sambacc.grpc.generated.control_pb2_grpc as _rpc
    import sambacc.grpc.generated.control_pb2 as _pb

    mock_grpc_server.backend._kaboom = FileNotFoundError("ctdb")
    with grpc.insecure_channel(mock_grpc_server.address) as channel:
        client = _rpc.SambaControlStub(channel)
        res = client.GetDebugLevel(
            _pb.GetDebugLevelRequest(
                process=_pb.SMB_PROCESS_CTDB,
            )
        )
    assert res.process == _pb.SMB_PROCESS_CTDB
    assert res.debug_level == "ERROR"
    assert mock_grpc_server.backend._counter["get_debug_level"] == 1


ctdb_status1 = """
{
  "node_status": {
    "node_count": 3,
    "deleted_node_count": 0,
    "nodes": {
      "0": {
        "pnn": 0,
        "address": "192.168.76.202",
        "partially_online": false,
        "flags_raw": 0,
        "flags_ok": true,
        "flags": {
          "disconnected": false,
          "unknown": false,
          "disabled": false,
          "banned": false,
          "unhealthy": false,
          "deleted": false,
          "stopped": false,
          "inactive": false
        },
        "this_node": false
      },
      "1": {
        "pnn": 1,
        "address": "192.168.76.201",
        "partially_online": false,
        "flags_raw": 0,
        "flags_ok": true,
        "flags": {
          "disconnected": false,
          "unknown": false,
          "disabled": false,
          "banned": false,
          "unhealthy": false,
          "deleted": false,
          "stopped": false,
          "inactive": false
        },
        "this_node": false
      },
      "2": {
        "pnn": 2,
        "address": "192.168.76.200",
        "partially_online": false,
        "flags_raw": 0,
        "flags_ok": true,
        "flags": {
          "disconnected": false,
          "unknown": false,
          "disabled": false,
          "banned": false,
          "unhealthy": false,
          "deleted": false,
          "stopped": false,
          "inactive": false
        },
        "this_node": true
      }
    }
  },
  "vnn_status": {
    "generation": 2139459491,
    "size": 3,
    "vnn_map": [
      {
        "hash": 0,
        "lmaster": 0
      },
      {
        "hash": 1,
        "lmaster": 1
      },
      {
        "hash": 2,
        "lmaster": 2
      }
    ]
  },
  "recovery_mode": "NORMAL",
  "recovery_mode_raw": 0,
  "leader": 0
}
"""


def test_ctdb_status_parse():
    try:
        import sambacc.grpc.conversions
    except ImportError:
        pytest.skip("can not import grpc conversions")

    obj = backend.CTDBStatus.parse(ctdb_status1)
    assert len(obj.node_status.nodes) == 3
    assert len(obj.vnn_status.vnn_map) == 3

    # test pb conversion too
    pbobj = sambacc.grpc.conversions.ctdb_status(obj)
    assert len(pbobj.node_status.nodes) == 3
    assert len(pbobj.vnn_status.vnn_map) == 3


# real output for net clusterlevel show --json
clusterlevel_show1 = """\
{"active_level": {"major": 1, "minor": 0}}
"""

# cluster already at max level, no upgrade available
clusterlevel_showall1 = """\
{
    "active_level": {"major": 1, "minor": 0},
    "nodes": [
        {"pnn": 0, "supported_ranges": [
            {"major": 1, "minor_min": 0, "minor_max": 0}]},
        {"pnn": 1, "supported_ranges": [
            {"major": 1, "minor_min": 0, "minor_max": 0}]},
        {"pnn": 2, "supported_ranges": [
            {"major": 1, "minor_min": 0, "minor_max": 0}]}
    ],
    "upgrade_possible": false
}
"""

# all nodes agree on a higher level -> upgrade possible
clusterlevel_showall2_upgrade_possible = """\
{
    "active_level": {"major": 1, "minor": 0},
    "nodes": [
        {"pnn": 0, "supported_ranges": [
            {"major": 2, "minor_min": 0, "minor_max": 0}]},
        {"pnn": 1, "supported_ranges": [
            {"major": 2, "minor_min": 0, "minor_max": 0}]}
    ],
    "upgrade_possible": true,
    "highest_level": {"major": 2, "minor": 0}
}
"""

# nodes disagree, a higher level exists but isn't possible yet
clusterlevel_showall3_nodes_disagree = """\
{
    "active_level": {"major": 1, "minor": 0},
    "nodes": [
        {"pnn": 0, "supported_ranges": [
            {"major": 2, "minor_min": 0, "minor_max": 0}]},
        {"pnn": 1, "supported_ranges": [
            {"major": 1, "minor_min": 0, "minor_max": 0}]}
    ],
    "upgrade_possible": false,
    "highest_level": {"major": 2, "minor": 0}
}
"""

# real output for cluster already at its highest level, --test (dry run)
clusterlevel_upgrade_already_current = """\
{"dry_run": true, "status": "already_current",
 "old_level": {"major": 1, "minor": 0}}
"""

# dry run reporting what an actual upgrade would do
clusterlevel_upgrade_dry_run_ok = """\
{
    "dry_run": true,
    "status": "dry_run_ok",
    "old_level": {"major": 1, "minor": 0},
    "new_level": {"major": 2, "minor": 0}
}
"""

# --apply actually committed the upgrade
clusterlevel_upgrade_upgraded = """\
{
    "dry_run": false,
    "status": "upgraded",
    "old_level": {"major": 1, "minor": 0},
    "new_level": {"major": 2, "minor": 0}
}
"""

# upgrade attempted but failed on one node
clusterlevel_upgrade_error = """\
{
    "dry_run": false,
    "status": "error",
    "error_vnn": 2,
    "error_status": "NT_STATUS_UNSUCCESSFUL"
}
"""

# real output for net clusterlevel features --json
clusterlevel_features1 = """\
{
    "cluster_support": true,
    "ctdb_socket": "/run/samba/ctdb/ctdbd.socket",
    "ctdb_protocol": 1,
    "supported_ranges": [
        {"major": 1, "minor_min": 0, "minor_max": 0}
    ]
}
"""


def test_cluster_level_parse_show():
    obj = backend.ClusterFunctionalLevel.parse_show(clusterlevel_show1)
    assert obj == backend.ClusterFunctionalLevel(major=1, minor=0)


def test_cluster_level_parse_showall():
    try:
        import sambacc.grpc.conversions
    except ImportError:
        pytest.skip("can not import grpc conversions")

    obj = backend.ClusterLevelInfo.parse_showall(clusterlevel_showall1)
    assert obj.active_level == backend.ClusterFunctionalLevel(major=1, minor=0)
    assert len(obj.nodes) == 3
    assert obj.nodes[0].pnn == 0
    assert obj.nodes[0].supported_ranges == [
        backend.ClusterLevelRange(major=1, minor_min=0, minor_max=0)
    ]
    assert not obj.upgrade_possible
    assert obj.highest_level is None

    # test pb conversion too
    pbobj = sambacc.grpc.conversions.cluster_level_info(obj)
    assert pbobj.active_level.major == 1
    assert pbobj.active_level.minor == 0
    assert len(pbobj.nodes) == 3
    assert not pbobj.upgrade_possible


def test_cluster_level_parse_showall_upgrade_possible():
    obj = backend.ClusterLevelInfo.parse_showall(
        clusterlevel_showall2_upgrade_possible
    )
    assert obj.active_level == backend.ClusterFunctionalLevel(major=1, minor=0)
    assert len(obj.nodes) == 2
    assert obj.upgrade_possible
    assert obj.highest_level == backend.ClusterFunctionalLevel(
        major=2, minor=0
    )


def test_cluster_level_parse_showall_nodes_disagree():
    obj = backend.ClusterLevelInfo.parse_showall(
        clusterlevel_showall3_nodes_disagree
    )
    assert obj.active_level == backend.ClusterFunctionalLevel(major=1, minor=0)
    assert len(obj.nodes) == 2
    # a higher level exists on some node, but not for all so not eligible yet
    assert not obj.upgrade_possible
    assert obj.highest_level == backend.ClusterFunctionalLevel(
        major=2, minor=0
    )


def test_cluster_level_parse_showall_invalid_json():
    with pytest.raises(ValueError):
        backend.ClusterLevelInfo.parse_showall("garbage output\n")


def test_cluster_level_parse_showall_no_active_level():
    with pytest.raises(KeyError):
        backend.ClusterLevelInfo.parse_showall('{"nodes": []}')


def test_cluster_level_upgrade_parse_already_current():
    obj = backend.ClusterLevelUpgradeResult.parse_upgrade(
        clusterlevel_upgrade_already_current
    )
    assert obj.dry_run
    assert obj.status == "already_current"
    assert obj.old_level == backend.ClusterFunctionalLevel(major=1, minor=0)
    assert obj.new_level is None
    assert obj.error_vnn is None
    assert obj.error_status is None


def test_cluster_level_upgrade_parse_dry_run_ok():
    obj = backend.ClusterLevelUpgradeResult.parse_upgrade(
        clusterlevel_upgrade_dry_run_ok
    )
    assert obj.dry_run
    assert obj.status == "dry_run_ok"
    assert obj.old_level == backend.ClusterFunctionalLevel(major=1, minor=0)
    assert obj.new_level == backend.ClusterFunctionalLevel(major=2, minor=0)


def test_cluster_level_upgrade_parse_upgraded():
    obj = backend.ClusterLevelUpgradeResult.parse_upgrade(
        clusterlevel_upgrade_upgraded
    )
    assert not obj.dry_run
    assert obj.status == "upgraded"
    assert obj.old_level == backend.ClusterFunctionalLevel(major=1, minor=0)
    assert obj.new_level == backend.ClusterFunctionalLevel(major=2, minor=0)


def test_cluster_level_upgrade_parse_error():
    obj = backend.ClusterLevelUpgradeResult.parse_upgrade(
        clusterlevel_upgrade_error
    )
    assert not obj.dry_run
    assert obj.status == "error"
    assert obj.old_level is None
    assert obj.new_level is None
    assert obj.error_vnn == 2
    assert obj.error_status == "NT_STATUS_UNSUCCESSFUL"


def test_cluster_level_features_parse():
    obj = backend.ClusterLevelFeatures.parse_features(clusterlevel_features1)
    assert obj.cluster_support
    assert obj.ctdb_socket == "/run/samba/ctdb/ctdbd.socket"
    assert obj.ctdb_protocol == 1
    assert obj.supported_ranges == [
        backend.ClusterLevelRange(major=1, minor_min=0, minor_max=0)
    ]


def test_clusterlevel_json_error_on_stdout():
    stdout = b'{"error":"Unable to connect to local ctdbd."}'
    assert (
        backend._clusterlevel_error(stdout, b"")
        == "Unable to connect to local ctdbd."
    )


def test_clusterlevel_error_stderr_fallback():
    assert backend._clusterlevel_error(b"", b"kaboom") == "kaboom"


def test_clusterlevel_error_stdout_fallback():
    assert backend._clusterlevel_error(b"not json", b"") == "not json"


def test_clusterlevel_error_no_output():
    assert backend._clusterlevel_error(b"", b"") == "no output"
