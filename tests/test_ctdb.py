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

# import pytest

import sambacc.config
import sambacc.samba_cmds
from sambacc import ctdb


def test_migrate_tdb(tmpdir, monkeypatch):
    src = tmpdir / "src"
    os.mkdir(src)
    dst = tmpdir / "dst"
    os.mkdir(dst)
    fake = tmpdir / "fake.sh"
    monkeypatch.setattr(ctdb, "_SRC_TDB_DIRS", [str(src)])
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    with open(fake, "w") as fh:
        fh.write("#!/bin/sh\n")
        fh.write('[ "$1" == "ltdbtool" ] || exit 1\n')
        fh.write('[ "$2" == "convert" ] || exit 1\n')
        fh.write('exec cp "$4" "$5"\n')
    os.chmod(fake, 0o755)

    with open(src / "registry.tdb", "w") as fh:
        fh.write("fake")
    with open(src / "passdb.tdb", "w") as fh:
        fh.write("fake")
    with open(src / "mango.tdb", "w") as fh:
        fh.write("fake")

    ctdb.migrate_tdb(None, str(dst))

    assert os.path.exists(dst / "registry.tdb.0")
    assert os.path.exists(dst / "passdb.tdb.0")
    assert not os.path.exists(dst / "mango.tdb.0")


def test_ensure_ctdbd_etc_files(tmpdir):
    src = tmpdir / "src"
    os.mkdir(src)
    dst = tmpdir / "dst"
    os.mkdir(dst)

    # this largely just creates a bunch of symlinks so it doesn't
    # need much fakery.
    ctdb.ensure_ctdbd_etc_files(etc_path=dst, src_path=src)
    assert os.path.islink(dst / "functions")
    assert os.path.islink(dst / "notify.sh")
    assert os.path.islink(dst / "events/legacy/00.ctdb.script")
