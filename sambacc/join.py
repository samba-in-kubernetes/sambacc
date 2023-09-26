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
import errno
import json
import logging
import subprocess
import typing

from .opener import Opener, FileOpener
from sambacc import samba_cmds
from sambacc.simple_waiter import Waiter

_logger = logging.getLogger(__name__)


class JoinError(Exception):
    def __init__(self, v: typing.Any) -> None:
        super().__init__(v)
        self.errors: list[typing.Any] = []


_PROMPT = object()
_PT = typing.TypeVar("_PT")
_PW = typing.Union[str, _PT]


class JoinBy(enum.Enum):
    PASSWORD = "password"
    FILE = "file"
    INTERACTIVE = "interactive"


class UserPass:
    """Encapsulate a username/password pair."""

    username: str = "Administrator"
    password: typing.Optional[_PW] = None

    def __init__(
        self,
        username: typing.Optional[str] = None,
        password: typing.Optional[_PW] = None,
    ) -> None:
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password


class _JoinSource(typing.NamedTuple):
    method: JoinBy
    upass: typing.Optional[UserPass]
    path: str


class Joiner:
    """Utility class for joining to AD domain.

    Use the `add_source` method to add one or more sources of join auth
    data. Call `join` to commit and join the "host" to AD.
    """

    _net_ads_join = samba_cmds.net["ads", "join"]

    def __init__(
        self,
        marker: typing.Optional[str] = None,
        *,
        opener: typing.Optional[Opener] = None,
    ) -> None:
        self._source_paths: list[str] = []
        self._sources: list[_JoinSource] = []
        self.marker = marker
        self._opener = opener or FileOpener()

    def add_source(
        self,
        method: JoinBy,
        value: typing.Optional[typing.Union[str, UserPass]] = None,
    ) -> None:
        if method in {JoinBy.PASSWORD, JoinBy.INTERACTIVE}:
            if not isinstance(value, UserPass):
                raise ValueError("expected UserPass value")
            if method == JoinBy.PASSWORD:
                self.add_pw_source(value)
            else:
                self.add_interactive_source(value)
        elif method in {JoinBy.FILE}:
            if not isinstance(value, str):
                raise ValueError("expected str value")
            self.add_file_source(value)
        else:
            raise ValueError(f"invalid method: {method}")

    def add_file_source(self, path_or_uri: str) -> None:
        self._sources.append(_JoinSource(JoinBy.FILE, None, path_or_uri))

    def add_pw_source(self, value: UserPass) -> None:
        self._sources.append(_JoinSource(JoinBy.PASSWORD, value, ""))

    def add_interactive_source(self, value: UserPass) -> None:
        self._sources.append(_JoinSource(JoinBy.INTERACTIVE, value, ""))

    def join(self, dns_updates: bool = False) -> None:
        if not self._sources:
            raise JoinError("no sources for join data")
        errors = []
        for src in self._sources:
            try:
                if src.method is JoinBy.PASSWORD:
                    assert src.upass
                    upass = src.upass
                elif src.method is JoinBy.FILE:
                    assert src.path
                    upass = self._read_from(src.path)
                elif src.method is JoinBy.INTERACTIVE:
                    assert src.upass
                    upass = UserPass(src.upass.username, _PROMPT)
                else:
                    raise ValueError(f"invalid method: {src.method}")
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

    def _read_from(self, path: str) -> UserPass:
        try:
            with self._opener.open(path) as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise JoinError(f"source file not found: {path}")
        except OSError as err:
            if getattr(err, "errno", 0) != errno.ENOENT:
                raise
            raise JoinError(f"resource not found: {path}")
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

    def _interactive_input(self) -> typing.Optional[typing.IO]:
        return None

    def _join(self, upass: UserPass, dns_updates: bool = False) -> None:
        args = []
        if not dns_updates:
            args.append("--no-dns-updates")
        args.extend(["-U", upass.username])

        if upass.password is _PROMPT:
            cmd = list(self._net_ads_join[args])
            proc = subprocess.Popen(cmd, stdin=self._interactive_input())
        else:
            cmd = list(self._net_ads_join[args])
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            pw_data = samba_cmds.encode(upass.password)
            # mypy can't seem to handle the following lines, and none of my web
            # searches turned up a clear answer. ignore for now
            proc.stdin.write(pw_data)  # type: ignore
            proc.stdin.write(b"\n")  # type: ignore
            proc.stdin.close()  # type: ignore
        ret = proc.wait()
        if ret != 0:
            raise JoinError("failed to run {}".format(cmd))

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


def join_when_possible(
    joiner: Joiner,
    waiter: Waiter,
    error_handler: typing.Optional[typing.Callable] = None,
) -> None:
    while True:
        if joiner.did_join():
            _logger.info("found valid join marker")
            return
        try:
            joiner.join()
            _logger.info("successful join")
            return
        except JoinError as err:
            if error_handler is not None:
                error_handler(err)
            else:
                raise
        waiter.wait()
