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

import sambacc.simple_waiter


def test_generate_sleeps():
    g = sambacc.simple_waiter.generate_sleeps()
    times = [next(g) for _ in range(130)]
    assert times[0] == 1
    assert times[0:11] == [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
    assert times[12] == 5
    assert all(times[x] == 5 for x in range(12, 33))
    assert times[34] == 60
    assert all(times[x] == 60 for x in range(34, 130))


def test_sleeper():
    def gen():
        while True:
            yield 8

    cc = 0

    def fake_sleep(v):
        nonlocal cc
        cc += 1
        assert v == 8

    sleeper = sambacc.simple_waiter.Sleeper(times=gen())
    sleeper._sleep = fake_sleep
    sleeper.wait()
    assert cc == 1
    for _ in range(3):
        sleeper.wait()
    assert cc == 4

    cc = 0

    def fake_sleep2(v):
        nonlocal cc
        cc += 1
        assert v == 1

    sleeper = sambacc.simple_waiter.Sleeper()
    sleeper._sleep = fake_sleep2
    sleeper.wait()
    assert cc == 1
    for _ in range(3):
        sleeper.wait()
    assert cc == 4
