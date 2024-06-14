#
# sambacc: a samba container configuration tool
# Copyright (C) 2023  John Mulligan
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

import typing


class SchemeNotSupported(Exception):
    pass


class Opener(typing.Protocol):
    """Protocol for a basic opener type that takes a path-ish or uri-ish
    string and tries to open it.
    """

    def open(self, path_or_uri: str) -> typing.IO:
        """Open a specified resource by path or (pseudo) URI."""
        ...  # pragma: no cover


class FallbackOpener:
    """FallbackOpener is used to open a path if a the string can not be
    opened as a URI/URL.
    """

    def __init__(
        self,
        openers: list[Opener],
        open_fn: typing.Optional[typing.Callable[..., typing.IO]] = None,
    ) -> None:
        self._openers = openers
        self._open_fn = open_fn or FileOpener.open

    def open(self, path_or_uri: str) -> typing.IO:
        for opener in self._openers:
            try:
                return opener.open(path_or_uri)
            except SchemeNotSupported:
                pass
        return self._open(path_or_uri)

    def _open(self, path: str) -> typing.IO:
        return self._open_fn(path)


class FileOpener:
    """Minimal opener that only supports opening local files."""

    @staticmethod
    def open(path: str) -> typing.IO:
        return open(path, "rb")
