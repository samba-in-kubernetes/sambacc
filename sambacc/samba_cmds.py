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
ArgList = typing.Optional[list[str]]

_GLOBAL_PREFIX: list[str] = []
_GLOBAL_DEBUG: str = ""


# Known flags for SAMBA_SPECIFICS env variable
_DAEMON_CLI_STDOUT_OPT: str = "daemon_cli_debug_output"
_CTDB_LEADER_ADMIN_CMD: str = "ctdb_leader_admin_command"


def get_samba_specifics() -> typing.Set[str]:
    value = os.environ.get("SAMBA_SPECIFICS", "")
    out = set()
    if value:
        for v in value.split(","):
            out.add(v)
    return out


def _daemon_stdout_opt(daemon: str) -> str:
    if daemon == "smbd":
        opt = "--log-stdout"
    else:
        opt = "--stdout"
    opt_lst = get_samba_specifics()
    if _DAEMON_CLI_STDOUT_OPT in opt_lst:
        opt = "--debug-stdout"
    return opt


def ctdb_leader_admin_cmd() -> str:
    leader_cmd = "recmaster"
    opt_lst = get_samba_specifics()
    if _CTDB_LEADER_ADMIN_CMD in opt_lst:
        leader_cmd = "leader"
    return leader_cmd


def set_global_prefix(lst: list[str]) -> None:
    _GLOBAL_PREFIX[:] = lst


def set_global_debug(level: str) -> None:
    global _GLOBAL_DEBUG
    _GLOBAL_DEBUG = level


def _to_args(value: typing.Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


class CommandArgs:
    """A utility class for building command line commands."""

    _name: str
    args: list[str]
    cmd_prefix: list[str]

    def __init__(self, name: str, args: ArgList = None):
        self._name = name
        self.args = args or []
        self.cmd_prefix = []

    def __getitem__(self, new_value: typing.Any) -> CommandArgs:
        return self.__class__(self._name, args=self.args + _to_args(new_value))

    def raw_args(self) -> list[str]:
        return [self._name] + self.args

    def prefix_args(self) -> list[str]:
        return list(_GLOBAL_PREFIX) + list(self.cmd_prefix)

    def argv(self) -> list[str]:
        return self.prefix_args() + self.raw_args()

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self.argv())

    def __repr__(self) -> str:
        return "CommandArgs({!r}, {!r})".format(self._name, self.args)

    @property
    def name(self) -> str:
        """Return the command to be executed. This may differ from
        the underlying command.
        """
        return self.argv()[0]


class SambaCommand(CommandArgs):
    """A utility class for building samba (or any) command line command."""

    debug: DebugLevel

    def __init__(
        self, name: str, args: ArgList = None, debug: DebugLevel = None
    ):
        super().__init__(name, args)
        self.debug = debug

    def __getitem__(self, new_value: typing.Any) -> SambaCommand:
        return self.__class__(
            self._name,
            args=self.args + _to_args(new_value),
            debug=self.debug,
        )

    def _debug_args(self, dlvl: str = "--debuglevel={}") -> list[str]:
        if self.debug:
            return [dlvl.format(self.debug)]
        if _GLOBAL_DEBUG:
            return [dlvl.format(_GLOBAL_DEBUG)]
        return []

    def raw_args(self) -> list[str]:
        return [self._name] + self.args + self._debug_args()

    def __repr__(self) -> str:
        return "SambaCommand({!r}, {!r}, {!r})".format(
            self._name, self.args, self.debug
        )


net = SambaCommand("net")

wbinfo = SambaCommand("wbinfo")

smbd = SambaCommand("/usr/sbin/smbd")

winbindd = SambaCommand("/usr/sbin/winbindd")

samba_dc = SambaCommand("/usr/sbin/samba")


def smbd_foreground() -> SambaCommand:
    return smbd[
        "--foreground", _daemon_stdout_opt("smbd"), "--no-process-group"
    ]


def winbindd_foreground() -> SambaCommand:
    return winbindd[
        "--foreground", _daemon_stdout_opt("winbindd"), "--no-process-group"
    ]


def samba_dc_foreground() -> SambaCommand:
    return samba_dc["--foreground", _daemon_stdout_opt("samba")]


ctdbd = SambaCommand("/usr/sbin/ctdbd")

ctdbd_foreground = ctdbd["--interactive"]

ltdbtool = CommandArgs("ltdbtool")

ctdb = SambaCommand("ctdb")

sambatool = SambaCommand("samba-tool")

smbcontrol = SambaCommand("smbcontrol")

ctdb_mutex_ceph_rados_helper = SambaCommand(
    "/usr/libexec/ctdb/ctdb_mutex_ceph_rados_helper"
)


def encode(value: typing.Union[str, bytes, None]) -> bytes:
    if value is None:
        return b""
    elif isinstance(value, str):
        value = value.encode("utf8")
    return value


def execute(cmd: SambaCommand) -> None:
    """Exec into the command specified (without forking)."""
    os.execvp(cmd.name, cmd.argv())  # pragma: no cover
