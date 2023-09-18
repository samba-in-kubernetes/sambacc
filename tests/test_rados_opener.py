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
    sambacc.rados_opener.enable_rados_url_opener(cls_mock)
    assert cls_mock._handlers.append.called


def test_enable_rados_url_opener_fail(monkeypatch):
    cls_mock = unittest.mock.MagicMock()
    sambacc.rados_opener.enable_rados_url_opener(cls_mock)
    assert not cls_mock._handlers.append.called


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
        _rados_api = None

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

    rr = sambacc.rados_opener._RADOSResponse(mock, "foo", "bar", "baz")
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

    rr = sambacc.rados_opener._RADOSResponse(mock, "foo", "bar", "baz")
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

    rr = sambacc.rados_opener._RADOSResponse(mock, "foo", "bar", "baz")
    with rr:
        result = [value for value in rr]
    assert result == [sval]
    with pytest.raises(ValueError):
        rr.read(8)


def test_rados_response_not_implemented():
    mock = unittest.mock.MagicMock()

    rr = sambacc.rados_opener._RADOSResponse(mock, "foo", "bar", "baz")
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
