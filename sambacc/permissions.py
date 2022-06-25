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

from __future__ import annotations

import contextlib
import datetime
import errno
import logging
import os
import typing

from sambacc import _xattr as xattr


_logger = logging.getLogger(__name__)


class PermissionsHandler(typing.Protocol):
    def has_status(self) -> bool:
        """Return true if the path has status metadata."""
        ...  # pragma: no cover

    def status_ok(self) -> bool:
        """Return true if status is OK (no changes are needed)."""
        ...  # pragma: no cover

    def update(self) -> None:
        """Update the permissions as needed."""
        ...  # pragma: no cover

    def path(self) -> str:
        """Return the path under consideration."""
        ...  # pragma: no cover


@contextlib.contextmanager
def _opendir(path: str) -> typing.Iterator[int]:
    dfd: int = os.open(path, os.O_DIRECTORY)
    try:
        yield dfd
        os.fsync(dfd)
    except OSError:
        os.sync()
        raise
    finally:
        os.close(dfd)


class NoopPermsHandler:
    def __init__(
        self,
        path: str,
        status_xattr: str,
        options: typing.Dict[str, str],
        root: str = "/",
    ) -> None:
        self._path = path

    def path(self) -> str:
        return self._path

    def has_status(self) -> bool:
        return False

    def status_ok(self) -> bool:
        return True

    def update(self) -> None:
        pass


class InitPosixPermsHandler:
    """Initialize posix permissions on a share (directory).

    This handler sets posix permissions only.

    It will only set the permissions when the status xattr does not
    match the expected prefix value. This prevents it from overwiting
    permissions that may have been changed intentionally after
    share initialization.
    """

    _default_mode = 0o777
    _default_status_prefix = "v1"

    def __init__(
        self,
        path: str,
        status_xattr: str,
        options: typing.Dict[str, str],
        root: str = "/",
    ) -> None:
        self._path = path
        self._root = root
        self._xattr = status_xattr
        try:
            self._mode = int(options["mode"], 8)
        except KeyError:
            self._mode = self._default_mode
        try:
            self._prefix = options["status_prefix"]
        except KeyError:
            self._prefix = self._default_status_prefix

    def path(self) -> str:
        return self._path

    def _full_path(self) -> str:
        return os.path.join(self._root, self._path.lstrip("/"))

    def has_status(self) -> bool:
        try:
            self._get_status()
            return True
        except KeyError:
            return False

    def status_ok(self) -> bool:
        try:
            sval = self._get_status()
        except KeyError:
            return False
        curr_prefix = sval.split("/")[0]
        return curr_prefix == self._prefix

    def update(self) -> None:
        if self.status_ok():
            return
        self._set_perms()
        self._set_status()

    def _get_status(self) -> str:
        path = self._full_path()
        _logger.debug("reading xattr %r: %r", self._xattr, path)
        try:
            value = xattr.get(path, self._xattr, nofollow=True)
        except OSError as err:
            if err.errno == errno.ENODATA:
                raise KeyError(self._xattr)
            raise
        return value.decode("utf8")

    def _set_perms(self) -> None:
        # yeah, this is really simple compared to all the state management
        # stuff.
        path = self._full_path()
        with _opendir(path) as dfd:
            os.fchmod(dfd, self._mode)

    def _timestamp(self) -> str:
        return datetime.datetime.now().strftime("%s")

    def _set_status(self) -> None:
        # we save the marker prefix followed by a timestamp as a debugging hint
        ts = self._timestamp()
        val = f"{self._prefix}/{ts}"
        path = self._full_path()
        _logger.debug("setting xattr %r=%r: %r", self._xattr, val, self._path)
        with _opendir(path) as dfd:
            xattr.set(dfd, self._xattr, val, nofollow=True)


class AlwaysPosixPermsHandler(InitPosixPermsHandler):
    """Works like the init handler, but always sets the permissions,
    even if the status xattr exists and is valid.
    May be useful for testing and debugging.
    """

    def update(self) -> None:
        self._set_perms()
        self._set_status()
