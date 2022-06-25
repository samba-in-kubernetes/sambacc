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
import typing

import inotify_simple as _inotify  # type: ignore

DEFAULT_TIMEOUT = 300


class INotify:
    """A waiter that monitors a file path for changes, based on inotify.

    Inotify is used to monitor the specified path for changes (writes).
    It stops waiting when the file is changed or the timeout is reached.

    A `print_func` can be specified as a simple logging method.
    """

    timeout: int = DEFAULT_TIMEOUT
    print_func = None

    def __init__(
        self,
        path: str,
        print_func: typing.Optional[typing.Callable] = None,
        timeout: typing.Optional[int] = None,
    ) -> None:
        if timeout is not None:
            self.timeout = timeout
        self.print_func = print_func
        self._inotify = _inotify.INotify()
        dirpath, fpath = os.path.split(path)
        if not dirpath:
            dirpath = "."
        if not fpath:
            raise ValueError("a file path is required")
        self._dir = dirpath
        self._name = fpath
        self._mask = _inotify.flags.DELETE | _inotify.flags.CLOSE_WRITE
        self._inotify.add_watch(self._dir, self._mask)

    def close(self) -> None:
        self._inotify.close()

    def _print(self, msg: str) -> None:
        if self.print_func:
            self.print_func("[inotify waiter] {}".format(msg))

    def acted(self) -> None:
        return  # noop for inotify waiter

    def wait(self) -> None:
        next(self._wait())

    def _get_events(self) -> list[typing.Any]:
        timeout = 1000 * self.timeout
        self._print("waiting {}ms for activity...".format(timeout))
        events = self._inotify.read(timeout=timeout)
        if not events:
            # use "None" as a sentinel for a timeout, otherwise we can not
            # tell if its all events that didn't match or a true timeout
            return [None]
        # filter out events we don't care about
        return [
            event
            for event in events
            if (event.name == self._name)
            and ((event.mask & _inotify.flags.CLOSE_WRITE) != 0)
        ]

    def _wait(self) -> typing.Iterator[None]:
        while True:
            for event in self._get_events():
                if event is None:
                    self._print("timed out")
                    yield None
                else:
                    self._print(f"{self._name} modified")
                    yield None
