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
import typing


def generate_sleeps() -> typing.Iterator[int]:
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

    def __init__(
        self, times: typing.Optional[typing.Iterator[int]] = None
    ) -> None:
        if times is None:
            times = generate_sleeps()
        self._times = times
        self._sleep = time.sleep

    def wait(self) -> None:
        self._sleep(next(self._times))

    def acted(self) -> None:
        """Inform the sleeper the caller reacted to a change and
        the sleeps should be reset.
        """
        self.times = generate_sleeps()


class Waiter(typing.Protocol):
    """Waiter protocol - interfaces common to all waiters."""

    def wait(self) -> None:
        """Pause execution for a time."""
        ...  # pragma: no cover

    def acted(self) -> None:
        """Inform that waiter that changes were made."""
        ...  # pragma: no cover


def watch(
    waiter: Waiter,
    initial_value: typing.Any,
    fetch_func: typing.Callable[..., typing.Any],
    compare_func: typing.Callable[..., typing.Tuple[typing.Any, bool]],
) -> None:
    """A very simple "event loop" that fetches current data with
    `fetch_func`, compares and updates state with `compare_func` and
    then waits for new events with `pause_func`.
    """
    previous = initial_value
    while True:
        try:
            previous, updated = compare_func(fetch_func(), previous)
        except FileNotFoundError:
            updated = False
            previous = None
        try:
            if updated:
                waiter.acted()
            waiter.wait()
        except KeyboardInterrupt:
            return
