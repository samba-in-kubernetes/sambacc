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


@pytest.fixture()
def mock_grpc_server():
    try:
        import sambacc.grpc.server
    except ImportError:
        pytest.skip("can not import grpc server")

    class TestConfig(sambacc.grpc.server.ServerConfig):
        max_workers = 3
        address = "localhost:54445"
        insecure = True
        _server = None
        backend = None

        def wait(self, server):
            self._server = server

    tc = TestConfig()
    tc.backend = MockBackend()
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
