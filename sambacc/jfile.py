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
"""Utilities for working with JSON data stored in a file system file.
"""

import fcntl
import json
import os
import typing

from sambacc.typelets import ExcType, ExcValue, ExcTraceback, Self

OPEN_RO = os.O_RDONLY
OPEN_RW = os.O_CREAT | os.O_RDWR


def open(path: str, flags: int, mode: int = 0o644) -> typing.IO:
    """A wrapper around open to open JSON files for read or read/write.
    `flags` must be os.open type flags. Use `OPEN_RO` and `OPEN_RW` for
    convenience.
    """
    return os.fdopen(os.open(path, flags, mode), "r+")


def load(
    fh: typing.IO, default: typing.Optional[dict[str, typing.Any]] = None
) -> typing.Any:
    """Similar to json.load, but returns the `default` value if fh refers to an
    empty file. fh must be seekable."""
    if fh.read(4) == "":
        # probe it to see if its an empty file
        data = default
    else:
        fh.seek(0)
        data = json.load(fh)
    return data


def dump(data: typing.Any, fh: typing.IO) -> None:
    """Similar to json.dump, but truncates the file before writing in order
    to avoid appending data to the file. fh must be seekable.
    """
    fh.seek(0)
    fh.truncate(0)
    json.dump(data, fh)


def flock(fh: typing.IO) -> None:
    """A simple wrapper around flock."""
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


class ClusterMetaJSONHandle:
    def __init__(self, fh: typing.IO) -> None:
        self._fh = fh

    def load(self) -> typing.Any:
        return load(self._fh, {})

    def dump(self, data: typing.Any) -> None:
        dump(data, self._fh)
        self._fh.flush()
        os.fsync(self._fh)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: ExcType, exc_val: ExcValue, exc_tb: ExcTraceback
    ) -> None:
        self._fh.close()


class ClusterMetaJSONFile:
    def __init__(self, path: str) -> None:
        self.path = path

    def open(
        self, *, read: bool = True, write: bool = False, locked: bool = False
    ) -> ClusterMetaJSONHandle:
        if read and write:
            flags = OPEN_RW
        elif read:
            flags = OPEN_RO
        else:
            raise ValueError("write-only not supported")
        fh = open(self.path, flags)
        try:
            if locked:
                flock(fh)
        except Exception:
            fh.close()
            raise
        return ClusterMetaJSONHandle(fh)
