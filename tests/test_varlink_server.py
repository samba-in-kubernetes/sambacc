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

import contextlib

import pytest


@pytest.fixture()
def mock_varlink_server(tmp_path):
    try:
        import sambacc.varlink.server
        import sambacc.varlink.keybridge
    except ImportError:
        pytest.skip("can not import varlink server")

    sockdir = tmp_path / "socket"
    sockpath = sockdir / "v.sock"
    sockdir.mkdir(parents=True, exist_ok=True)

    addr = f"unix:{sockpath.absolute()}"
    sambacc.varlink.server.patch_varlink_encoder()
    opts = sambacc.varlink.server.VarlinkServerOptions(addr)
    srv = sambacc.varlink.server.VarlinkServer(opts)
    mem_scope = sambacc.varlink.keybridge.MemScope()
    mem_scope.set(
        "example", sambacc.varlink.keybridge.EntryKind.VALUE, "nice one"
    )
    srv.add_endpoint(
        sambacc.varlink.keybridge.endpoint(
            [
                sambacc.varlink.keybridge.StaticValueScope(),
                mem_scope,
            ]
        )
    )
    with srv.serve():
        yield srv


@contextlib.contextmanager
def _keybridge_conn(address):
    import varlink  # type: ignore[import]

    with contextlib.ExitStack() as estack:
        client = estack.enter_context(varlink.Client(address))
        connection = estack.enter_context(
            client.open("org.samba.containers.keybridge")
        )
        yield connection


def test_scope_list(mock_varlink_server):
    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        result = connection.Scopes()
    assert len(result["scopes"]) == 2


def test_has_scope(mock_varlink_server):
    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        # first scope
        result = connection.HasScope("static_value_scope")
        assert "scope" in result
        assert result["scope"]["name"] == "static_value_scope"
        # second scope
        result = connection.HasScope("mem")
        assert "scope" in result
        assert result["scope"]["name"] == "mem"
        # missing scope
        result = connection.HasScope("foo")
        assert "scope" not in result


def test_get_invalid_scope(mock_varlink_server):
    import varlink
    from sambacc.varlink.keybridge import EntryKind

    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        with pytest.raises(varlink.VarlinkError):
            connection.Get("bob", "foo", EntryKind.VALUE)


def test_get_static_value(mock_varlink_server):
    from sambacc.varlink.keybridge import EntryKind

    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        result = connection.Get("foo", "static_value_scope", EntryKind.VALUE)
    assert "entry" in result
    assert "name" in result["entry"]
    assert result["entry"]["name"] == "foo"
    assert result["entry"]["data"] == "foo-opolis"


def test_set_static_value_badop(mock_varlink_server):
    import varlink

    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        with pytest.raises(varlink.VarlinkError):
            connection.Set(
                {
                    "name": "quux",
                    "scope": "static_value_scope",
                    "kind": "VALUE",
                    "data": "flippy",
                }
            )


def test_delete_static_value_badop(mock_varlink_server):
    import varlink

    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        with pytest.raises(varlink.VarlinkError):
            connection.Delete("quux", "static_value_scope")


def test_get_mem_missing(mock_varlink_server):
    import varlink
    from sambacc.varlink.keybridge import EntryKind

    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        with pytest.raises(varlink.VarlinkError):
            connection.Get("foo", "mem", EntryKind.VALUE)


def test_get_mem(mock_varlink_server):
    from sambacc.varlink.keybridge import EntryKind

    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        result = connection.Get("example", "mem", EntryKind.VALUE)
    assert "entry" in result
    assert "name" in result["entry"]
    assert result["entry"]["name"] == "example"
    assert result["entry"]["data"] == "nice one"


def test_set_mem(mock_varlink_server):
    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        connection.Set(
            {
                "name": "quux",
                "scope": "mem",
                "kind": "VALUE",
                "data": "flippy",
            }
        )


def test_delete_mem(mock_varlink_server):
    with _keybridge_conn(mock_varlink_server.options.address) as connection:
        connection.Delete("quux", "mem")
