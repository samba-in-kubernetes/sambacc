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

from __future__ import annotations

import os
import typing

DebugLevel = typing.Optional[str]
ArgList = typing.Optional[typing.List[str]]

_GLOBAL_PREFIX: typing.List[str] = []
_GLOBAL_DEBUG: str = ""


def set_global_prefix(lst: typing.List[str]) -> None:
    _GLOBAL_PREFIX[:] = lst


def set_global_debug(level: str) -> None:
    global _GLOBAL_DEBUG
    _GLOBAL_DEBUG = level


class SambaCommand:
    """A utility class for building samba (or any) command line command."""

    name: str
    args: typing.List[str]
    cmd_prefix: typing.List[str]
    debug: DebugLevel

    def __init__(
        self, name: str, args: ArgList = None, debug: DebugLevel = None
    ):
        self.name = name
        self.args = args or []
        self.debug = debug
        self.cmd_prefix = []

    def __getitem__(self, new_args) -> SambaCommand:
        if isinstance(new_args, str):
            new_args = [new_args]
        else:
            new_args = list(new_args)
        args = self.args + new_args
        return self.__class__(self.name, args=args, debug=self.debug)

    def _prefix(self) -> typing.List[str]:
        return list(_GLOBAL_PREFIX) + list(self.cmd_prefix)

    def argv(self) -> typing.List[str]:
        cmd = self._prefix() + [self.name]
        if self.debug:
            cmd.append("--debuglevel={}".format(self.debug))
        elif _GLOBAL_DEBUG:
            cmd.append("--debuglevel={}".format(_GLOBAL_DEBUG))
        return cmd + self.args

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self.argv())

    def __repr__(self):
        return "SambaCommand({!r}, {!r}, {!r})".format(
            self.name, self.args, self.debug
        )


net = SambaCommand("net")

wbinfo = SambaCommand("wbinfo")

smbd = SambaCommand("/usr/sbin/smbd")

winbindd = SambaCommand("/usr/sbin/winbindd")

smbd_foreground = smbd[
    "--foreground",
    "--log-stdout",
    "--no-process-group",
]

winbindd_foreground = winbindd[
    "--foreground",
    "--stdout",
    "--no-process-group",
]

ctdbd = SambaCommand("/usr/sbin/ctdbd")

ctdbd_foreground = ctdbd["--interactive"]

ltdbtool = SambaCommand("ltdbtool")

ctdb = SambaCommand("ctdb")


def encode(value: typing.Union[str, bytes, None]) -> bytes:
    if value is None:
        return b""
    elif isinstance(value, str):
        value = value.encode("utf8")
    return value


def execute(cmd: SambaCommand) -> None:
    """Exec into the command specified (without forking)."""
    os.execvp(cmd.name, cmd.argv())
