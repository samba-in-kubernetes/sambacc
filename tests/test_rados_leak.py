#
# sambacc: a samba container configuration tool
# Copyright (C) 2026  John Mulligan
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

import unittest.mock

import pytest

import sambacc.ceph.rados

# CAUTION: these tests mock the ceph rados API. The fake Rados connection
# counts connect/shutdown so we can assert that connections are released
# rather than accumulated.


@pytest.fixture(scope="function")
def fake_cluster_meta(monkeypatch):
    mock = unittest.mock.MagicMock()
    # empty object body -> load() returns {}
    mock.Rados.return_value.open_ioctx.return_value.read.return_value = b""
    monkeypatch.setitem(sambacc.ceph.rados._module, "rados", mock)

    interface = sambacc.ceph.rados._RADOSInterface()
    interface.api = mock
    interface.client_name = ""
    interface.full_name = False
    monkeypatch.setattr(
        sambacc.ceph.rados._RADOSHandler, "_interface", interface
    )

    cmo = sambacc.ceph.rados.ClusterMetaRADOSObject.create_from_uri(
        "rados://foo/bar/baz"
    )
    conn = mock.Rados.return_value
    ioctx = conn.open_ioctx.return_value
    return cmo, conn, ioctx


def test_cluster_meta_open_closes_connection(fake_cluster_meta):
    cmo, conn, ioctx = fake_cluster_meta

    with cmo.open() as handle:
        assert handle.load() == {}

    assert conn.connect.call_count == 1
    assert conn.shutdown.call_count == 1
    assert ioctx.close.call_count == 1


def test_cluster_meta_open_does_not_leak_across_iterations(fake_cluster_meta):
    # ctdb.monitor_cluster_meta_changes() reopens once per poll; every open
    # connects a fresh client, so connects and shutdowns must stay balanced.
    cmo, conn, ioctx = fake_cluster_meta

    iterations = 25
    for _ in range(iterations):
        with cmo.open(locked=True) as handle:
            handle.load()

    assert conn.connect.call_count == iterations
    assert conn.shutdown.call_count == iterations
    assert ioctx.close.call_count == iterations


def test_cluster_meta_open_closes_when_body_raises(fake_cluster_meta):
    cmo, conn, ioctx = fake_cluster_meta

    with pytest.raises(RuntimeError):
        with cmo.open(locked=True):
            raise RuntimeError("boom")

    assert ioctx.unlock.called
    assert conn.shutdown.call_count == 1
    assert ioctx.close.call_count == 1


def test_rados_object_ref_close_is_idempotent():
    mock = unittest.mock.MagicMock()
    rr = sambacc.ceph.rados.RADOSObjectRef(mock, "foo", "bar", "baz")
    conn = mock.Rados.return_value
    ioctx = conn.open_ioctx.return_value

    rr.close()
    rr.close()
    rr.close()

    assert ioctx.close.call_count == 1
    assert conn.shutdown.call_count == 1
