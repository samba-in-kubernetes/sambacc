#
# sambacc: a samba container configuration tool
# Copyright (C) 2023  John Mulligan
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

import io
import sys
import unittest.mock
import urllib.request

import pytest

import sambacc.rados_opener

# CAUTION: nearly all of these tests are based on mocking the ceph rados API.
# Testing this for real would require an operational ceph cluster and that's
# not happening for a simple set of unit tests!


def test_enable_rados_url_opener(monkeypatch):
    mock = unittest.mock.MagicMock()
    monkeypatch.setitem(sys.modules, "rados", mock)

    cls_mock = unittest.mock.MagicMock()
    sambacc.rados_opener.enable_rados(cls_mock)
    assert cls_mock._handlers.append.called


def test_enable_rados_url_opener_fail(monkeypatch):
    cls_mock = unittest.mock.MagicMock()
    sambacc.rados_opener.enable_rados(cls_mock)
    assert not cls_mock._handlers.append.called


def test_enable_rados_url_opener_with_args(monkeypatch):
    mock = unittest.mock.MagicMock()
    monkeypatch.setitem(sys.modules, "rados", mock)

    cls_mock = unittest.mock.MagicMock()
    cls_mock._handlers = []
    sambacc.rados_opener.enable_rados(cls_mock, client_name="user1")
    assert len(cls_mock._handlers) == 1
    assert isinstance(
        cls_mock._handlers[0]._interface, sambacc.rados_opener._RADOSInterface
    )
    assert cls_mock._handlers[0]._interface.api is mock
    assert cls_mock._handlers[0]._interface.client_name == "user1"
    assert not cls_mock._handlers[0]._interface.full_name
    ri = cls_mock._handlers[0]._interface
    ri.Rados()
    assert ri.api.Rados.call_args[1]["rados_id"] == "user1"
    assert ri.api.Rados.call_args[1]["name"] == ""
    assert (
        ri.api.Rados.call_args[1]["conffile"] == mock.Rados.DEFAULT_CONF_FILES
    )


def test_enable_rados_url_opener_with_args2(monkeypatch):
    mock = unittest.mock.MagicMock()
    monkeypatch.setitem(sys.modules, "rados", mock)

    cls_mock = unittest.mock.MagicMock()
    cls_mock._handlers = []
    sambacc.rados_opener.enable_rados(
        cls_mock, client_name="client.user1", full_name=True
    )
    assert len(cls_mock._handlers) == 1
    assert isinstance(
        cls_mock._handlers[0]._interface, sambacc.rados_opener._RADOSInterface
    )
    assert cls_mock._handlers[0]._interface.api is mock
    assert cls_mock._handlers[0]._interface.client_name == "client.user1"
    assert cls_mock._handlers[0]._interface.full_name
    ri = cls_mock._handlers[0]._interface
    ri.Rados()
    assert ri.api.Rados.call_args[1]["rados_id"] == ""
    assert ri.api.Rados.call_args[1]["name"] == "client.user1"
    assert (
        ri.api.Rados.call_args[1]["conffile"] == mock.Rados.DEFAULT_CONF_FILES
    )


def test_rados_handler_parse():
    class RH(sambacc.rados_opener._RADOSHandler):
        _rados_api = unittest.mock.MagicMock()

    rh = RH()
    rq = urllib.request.Request("rados://foo/bar/baz")
    rr = rh.rados_open(rq)
    assert rr._pool == "foo"
    assert rr._ns == "bar"
    assert rr._key == "baz"

    rq = urllib.request.Request("rados:///foo1/bar1/baz1")
    rr = rh.rados_open(rq)
    assert rr._pool == "foo1"
    assert rr._ns == "bar1"
    assert rr._key == "baz1"


def test_rados_handler_norados():
    # Generally, this shouldn't happen because the rados handler shouldn't
    # be added to the URLOpener if rados module was unavailable.
    class RH(sambacc.rados_opener._RADOSHandler):
        _interface = None

    rh = RH()
    rq = urllib.request.Request("rados://foo/bar/baz")
    with pytest.raises(sambacc.rados_opener.RADOSUnsupported):
        rh.rados_open(rq)


def test_rados_response_read_all():
    sval = b"Hello, World.\nI am a fake rados object.\n"

    def _read(_, size, off):
        if off < len(sval):
            return sval

    mock = unittest.mock.MagicMock()
    mock.Rados.return_value.open_ioctx.return_value.read.side_effect = _read

    rr = sambacc.rados_opener.RADOSObjectRef(mock, "foo", "bar", "baz")
    assert rr.readable()
    assert not rr.seekable()
    assert not rr.writable()
    assert not rr.isatty()
    assert rr.mode == "rb"
    assert rr.name == "baz"
    assert not rr.closed
    data = rr.read()
    assert data == sval
    assert rr.tell() == len(sval)
    rr.flush()
    rr.close()
    assert rr.closed


def test_rados_response_read_chunks():
    sval = b"a bad cat lives under the murky terrifying water"
    bio = io.BytesIO(sval)

    def _read(_, size, off):
        bio.seek(off)
        return bio.read(size)

    mock = unittest.mock.MagicMock()
    mock.Rados.return_value.open_ioctx.return_value.read.side_effect = _read

    rr = sambacc.rados_opener.RADOSObjectRef(mock, "foo", "bar", "baz")
    assert rr.readable()
    assert rr.read(8) == b"a bad ca"
    assert rr.read(8) == b"t lives "
    assert rr.read(8) == b"under th"


def test_rados_response_read_ctx_iter():
    sval = b"a bad cat lives under the murky terrifying water"
    bio = io.BytesIO(sval)

    def _read(_, size, off):
        bio.seek(off)
        return bio.read(size)

    mock = unittest.mock.MagicMock()
    mock.Rados.return_value.open_ioctx.return_value.read.side_effect = _read

    rr = sambacc.rados_opener.RADOSObjectRef(mock, "foo", "bar", "baz")
    with rr:
        result = [value for value in rr]
    assert result == [sval]
    with pytest.raises(ValueError):
        rr.read(8)


def test_rados_response_not_implemented():
    mock = unittest.mock.MagicMock()

    rr = sambacc.rados_opener.RADOSObjectRef(mock, "foo", "bar", "baz")
    with pytest.raises(NotImplementedError):
        rr.seek(10)
    with pytest.raises(NotImplementedError):
        rr.fileno()
    with pytest.raises(NotImplementedError):
        rr.readline()
    with pytest.raises(NotImplementedError):
        rr.readlines()
    with pytest.raises(NotImplementedError):
        rr.truncate()
    with pytest.raises(NotImplementedError):
        rr.write(b"zzzzz")
    with pytest.raises(NotImplementedError):
        rr.writelines([b"zzzzz"])


def test_rados_handler_config_key():
    class RH(sambacc.rados_opener._RADOSHandler):
        _interface = unittest.mock.MagicMock()

    mc = RH._interface.Rados.return_value.__enter__.return_value.mon_command
    mc.return_value = (0, b"rubber baby buggy bumpers", "")

    rh = RH()
    rq = urllib.request.Request("rados:mon-config-key:aa/bb/cc")
    rr = rh.rados_open(rq)
    assert isinstance(rr, io.BytesIO)
    assert rr.read() == b"rubber baby buggy bumpers"
    assert mc.called
    assert "aa/bb/cc" in mc.call_args[0][0]

    mc.reset_mock()
    mc.return_value = (2, b"", "no passing")
    rh = RH()
    rq = urllib.request.Request("rados:mon-config-key:xx/yy/zz")
    with pytest.raises(OSError) as pe:
        rh.rados_open(rq)
    assert getattr(pe.value, "errno", None) == 2
    assert mc.called
    assert "xx/yy/zz" in mc.call_args[0][0]
