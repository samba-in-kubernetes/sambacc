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

import enum
import json
import subprocess
import typing


class JoinError(Exception):
    def __init__(self, v):
        super().__init__(v)
        self.errors = []


def _utf8(s) -> bytes:
    return s.encode("utf8")


_PROMPT = object()


class JoinBy(enum.Enum):
    PASSWORD = "password"
    FILE = "file"
    INTERACTIVE = "interactive"


class UserPass:
    """Encapsulate a username/password pair."""

    username = "Administrator"
    password = None

    def __init__(self, username=None, password=None):
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password


class Joiner:
    """Utility class for joining to AD domain.

    Use the `add_source` method to add one or more sources of join auth
    data. Call `join` to commit and join the "host" to AD.
    """

    cmd_prefix = ["net", "ads"]

    def __init__(self, marker=None):
        self._sources = []
        self.marker = marker

    def _netcmd(self, *args, **kwargs):
        cmd = list(self.cmd_prefix)
        cmd.extend(args)
        return cmd, subprocess.Popen(cmd, **kwargs)

    def add_source(
        self, method: JoinBy, value: typing.Optional[str] = None
    ) -> None:
        if method in {JoinBy.PASSWORD, JoinBy.INTERACTIVE}:
            if not isinstance(value, UserPass):
                raise ValueError("expected UserPass value")
        elif method in {JoinBy.FILE}:
            if not isinstance(value, str):
                raise ValueError("expected str value")
        else:
            raise ValueError(f"invalid method: {method}")
        self._sources.append((method, value))

    def join(self, dns_updates=False) -> None:
        if not self._sources:
            raise JoinError("no sources for join data")
        errors = []
        for method, value in self._sources:
            try:
                if method is JoinBy.PASSWORD:
                    upass = value
                elif method is JoinBy.FILE:
                    upass = self._read_from(value)
                elif method is JoinBy.INTERACTIVE:
                    upass = UserPass(value.username, _PROMPT)
                else:
                    raise ValueError(f"invalid method: {method}")
                self._join(upass, dns_updates=dns_updates)
                self._set_marker()
                return
            except JoinError as join_err:
                errors.append(join_err)
        if errors:
            if len(errors) == 1:
                raise errors[0]
            err = JoinError("failed {} join attempts".format(len(errors)))
            err.errors = errors
            raise err

    def _read_from(self, path) -> UserPass:
        try:
            with open(path) as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise JoinError(f"source file not found: {path}")
        upass = UserPass()
        try:
            upass.username = data["username"]
            upass.password = data["password"]
        except KeyError as err:
            raise JoinError(f"invalid file content: {err}")
        if not isinstance(upass.username, str):
            raise JoinError("invalid file content: invalid username")
        if not isinstance(upass.password, str):
            raise JoinError("invalid file content: invalid password")
        return upass

    def _join(self, upass: UserPass, dns_updates=False) -> None:
        args = []
        if not dns_updates:
            args.append("--no-dns-updates")
        args.extend(["-U", upass.username])

        if upass.password is _PROMPT:
            cli, proc = self._netcmd("join", *args)
        else:
            cli, proc = self._netcmd("join", *args, stdin=subprocess.PIPE)
            proc.stdin.write(_utf8(upass.password))
            proc.stdin.write(b"\n")
            proc.stdin.close()
        ret = proc.wait()
        if ret != 0:
            raise JoinError("failed to run {}".format(cli))

    def _set_marker(self) -> None:
        if self.marker is not None:
            with open(self.marker, "w") as fh:
                json.dump({"joined": True}, fh)

    def did_join(self) -> bool:
        """Return true if the join marker exists and contains a true
        value in the joined key.
        """
        if self.marker is None:
            return False
        try:
            with open(self.marker) as fh:
                data = json.load(fh)
        except (ValueError, OSError):
            return False
        try:
            return data["joined"]
        except (TypeError, KeyError):
            return False
