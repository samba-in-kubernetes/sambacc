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

import pytest

from sambacc import jfile


def test_open(tmpdir):
    with pytest.raises(FileNotFoundError):
        jfile.open(tmpdir / "a.json", jfile.OPEN_RO)
    fh = jfile.open(tmpdir / "a.json", jfile.OPEN_RW)
    assert fh is not None
    fh.close()


def test_laod(tmpdir):
    with jfile.open(tmpdir / "a.json", jfile.OPEN_RW) as fh:
        data = jfile.load(fh, ["missing"])
    assert data == ["missing"]

    with open(tmpdir / "a.json", "w") as fh:
        fh.write('{"present": true}\n')
    with jfile.open(tmpdir / "a.json", jfile.OPEN_RW) as fh:
        data = jfile.load(fh, ["missing"])
    assert data == {"present": True}


def test_dump(tmpdir):
    with jfile.open(tmpdir / "a.json", jfile.OPEN_RW) as fh:
        jfile.dump({"something": "good"}, fh)

    with jfile.open(tmpdir / "a.json", jfile.OPEN_RO) as fh:
        data = jfile.load(fh)
    assert data == {"something": "good"}

    with jfile.open(tmpdir / "a.json", jfile.OPEN_RW) as fh:
        jfile.dump({"something": "better"}, fh)

    with jfile.open(tmpdir / "a.json", jfile.OPEN_RO) as fh:
        data = jfile.load(fh)
    assert data == {"something": "better"}


def test_flock(tmpdir):
    import time
    import threading

    def sleepy_update(path):
        with jfile.open(path, jfile.OPEN_RW) as fh:
            jfile.flock(fh)
            data = jfile.load(fh, [0])
            time.sleep(0.2)
            data.append(data[-1] + 1)
            jfile.dump(data, fh)

    fpath = tmpdir / "a.json"
    t1 = threading.Thread(target=sleepy_update, args=(fpath,))
    t1.start()
    t2 = threading.Thread(target=sleepy_update, args=(fpath,))
    t2.start()
    t1.join()
    t2.join()

    with jfile.open(fpath, jfile.OPEN_RW) as fh:
        jfile.flock(fh)
        data = jfile.load(fh)
    assert data == [0, 1, 2]
