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

import contextlib
import threading
import time

import pytest

try:
    import sambacc.inotify_waiter
except ImportError:
    pytestmark = pytest.mark.skip


@contextlib.contextmanager
def background(bg_func):
    t = threading.Thread(target=bg_func)
    t.start()
    try:
        yield None
    finally:
        t.join()


def test_inotify(tmp_path):
    tfile = str(tmp_path / "foobar.txt")
    tfile2 = str(tmp_path / "other.txt")

    iw = sambacc.inotify_waiter.INotify(tfile, print_func=print, timeout=3)

    def _touch():
        time.sleep(0.2)
        with open(tfile, "w") as fh:
            print("W", tfile)
            fh.write("one")

    with background(_touch):
        before = time.time()
        iw.wait()
        after = time.time()
    assert after - before > 0.1
    assert after - before <= 1

    def _touch2():
        time.sleep(0.2)
        with open(tfile2, "w") as fh:
            print("W", tfile2)
            fh.write("two")
        time.sleep(1)
        with open(tfile, "w") as fh:
            print("W", tfile)
            fh.write("one")

    with background(_touch2):
        before = time.time()
        iw.wait()
        after = time.time()

    assert after - before > 0.1
    assert after - before >= 1

    before = time.time()
    iw.wait()
    after = time.time()
    assert int(after) - int(before) == 3
    iw.close()


def test_inotify_bad_input():
    with pytest.raises(ValueError):
        sambacc.inotify_waiter.INotify("/")


def test_inotify_relative_path():
    iw = sambacc.inotify_waiter.INotify("cool.txt")
    assert iw._dir == "."
    assert iw._name == "cool.txt"
