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

import os
import pytest

import sambacc.paths


def test_ensure_samba_dirs_fail(tmp_path):
    # This is missing both "var/lib" and "run"
    with pytest.raises(OSError):
        sambacc.paths.ensure_samba_dirs(root=tmp_path)
    os.mkdir(tmp_path / "var")
    os.mkdir(tmp_path / "var/lib")
    # This is missing "run"
    with pytest.raises(OSError):
        sambacc.paths.ensure_samba_dirs(root=tmp_path)


def test_ensure_samba_dirs_ok(tmp_path):
    os.mkdir(tmp_path / "var")
    os.mkdir(tmp_path / "var/lib")
    os.mkdir(tmp_path / "run")
    sambacc.paths.ensure_samba_dirs(root=tmp_path)


def test_ensure_samba_dirs_already(tmp_path):
    os.mkdir(tmp_path / "var")
    os.mkdir(tmp_path / "var/lib")
    os.mkdir(tmp_path / "var/lib/samba")
    os.mkdir(tmp_path / "var/lib/samba/private")
    os.mkdir(tmp_path / "run")
    os.mkdir(tmp_path / "run/samba/")
    os.mkdir(tmp_path / "run/samba/winbindd")
    sambacc.paths.ensure_samba_dirs(root=tmp_path)


def test_ensure_share_dirs(tmp_path):
    assert not os.path.exists(tmp_path / "foobar")
    sambacc.paths.ensure_share_dirs("foobar", root=str(tmp_path))
    assert os.path.exists(tmp_path / "foobar")

    assert not os.path.exists(tmp_path / "wibble")
    sambacc.paths.ensure_share_dirs("/wibble/cat", root=str(tmp_path))
    assert os.path.exists(tmp_path / "wibble/cat")
    sambacc.paths.ensure_share_dirs("/wibble/cat", root=str(tmp_path))
    assert os.path.exists(tmp_path / "wibble/cat")
