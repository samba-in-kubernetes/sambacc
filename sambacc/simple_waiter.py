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

import time


def generate_sleeps():
    """Generate sleep times starting with short sleeps and then
    getting longer. This assumes that resources may take a bit of
    time to settle, but eventually reach a steadier state and don't
    require being checked as often.
    """
    total = 0
    while True:
        if total > 120:
            val = 60
        elif total > 10:
            val = 5
        else:
            val = 1
        yield val
        total += val


# It's a bit overkill to have a class for this but I didn't like messing
# around with functools.partial or functions returning functions for this.
# It's also nice to replace the sleep function for unit tests.
class Sleeper:
    """It waits only by sleeping. Nothing fancy."""

    def __init__(self, times=None):
        if times is None:
            times = generate_sleeps()
        self._times = times
        self._sleep = time.sleep

    def wait(self):
        self._sleep(next(self._times))
