#
# sambacc: a samba container configuration tool
# Copyright (C) 2022  John Mulligan
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

import os

import pytest


import sambacc.permissions


@pytest.mark.parametrize(
    "cls",
    [
        sambacc.permissions.NoopPermsHandler,
        sambacc.permissions.InitPosixPermsHandler,
        sambacc.permissions.AlwaysPosixPermsHandler,
    ],
)
def test_permissions_path(cls):
    assert cls("/foo", "user.foo", options={}).path() == "/foo"


def test_noop_handler():
    nh = sambacc.permissions.NoopPermsHandler("/foo", "user.foo", options={})
    assert nh.path() == "/foo"
    assert not nh.has_status()
    assert nh.status_ok()
    assert nh.update() is None


@pytest.fixture(scope="function")
def tmp_path_xattrs_ok(tmp_path_factory):
    try:
        import xattr  # type: ignore
    except ImportError:
        pytest.skip("xattr module not available")

    tmpp = tmp_path_factory.mktemp("needs_xattrs")
    try:
        xattr.set(str(tmpp), "user.deleteme", "1")
        xattr.remove(str(tmpp), "user.deleteme")
    except OSError:
        raise pytest.skip(
            "temp dir does not support xattrs"
            " (try changing basetmp to a file system that supports xattrs)"
        )
    return tmpp


def test_init_handler(tmp_path_xattrs_ok):
    path = tmp_path_xattrs_ok / "foo"
    os.mkdir(path)
    ih = sambacc.permissions.InitPosixPermsHandler(
        str(path), "user.marker", options={}
    )
    assert ih.path().endswith("/foo")
    assert not ih.has_status()
    assert not ih.status_ok()

    ih.update()
    assert ih.has_status()
    assert ih.status_ok()

    os.chmod(path, 0o755)
    ih.update()
    assert (os.stat(path).st_mode & 0o777) == 0o755


def test_always_handler(tmp_path_xattrs_ok):
    path = tmp_path_xattrs_ok / "foo"
    os.mkdir(path)
    ih = sambacc.permissions.AlwaysPosixPermsHandler(
        str(path), "user.marker", options={}
    )
    assert ih.path().endswith("/foo")
    assert not ih.has_status()
    assert not ih.status_ok()

    ih.update()
    assert ih.has_status()
    assert ih.status_ok()

    os.chmod(path, 0o755)
    assert (os.stat(path).st_mode & 0o777) == 0o755
    ih.update()
    assert (os.stat(path).st_mode & 0o777) == 0o777
