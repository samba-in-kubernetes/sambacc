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

import typing

from .textfile import TextFileLoader
from sambacc import config


class LineFileLoader(TextFileLoader):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.lines: list[str] = []

    def loadlines(self, lines: typing.Iterable[str]) -> None:
        """Load in the lines from the text source."""
        for line in lines:
            self.lines.append(line)

    def dumplines(self) -> typing.Iterable[str]:
        """Dump the file content as lines of text."""
        prev = None
        for line in self.lines:
            if prev and not prev.endswith("\n"):
                yield "\n"
            yield line
            prev = line


class PasswdFileLoader(LineFileLoader):
    def __init__(self, path: str = "/etc/passwd") -> None:
        super().__init__(path)
        self._usernames: set[str] = set()

    def readfp(self, fp: typing.IO) -> None:
        super().readfp(fp)
        self._update_usernames_cache()

    def _update_usernames_cache(self) -> None:
        for line in self.lines:
            if ":" in line:
                u = line.split(":")[0]
                self._usernames.add(u)

    def add_user(self, user_entry: config.UserEntry) -> None:
        if user_entry.username in self._usernames:
            return
        line = "{}\n".format(":".join(user_entry.passwd_fields()))
        self.lines.append(line)
        self._usernames.add(user_entry.username)


class GroupFileLoader(LineFileLoader):
    def __init__(self, path: str = "/etc/group") -> None:
        super().__init__(path)
        self._groupnames: set[str] = set()

    def readfp(self, fp: typing.IO) -> None:
        super().readfp(fp)
        self._update_groupnames_cache()

    def _update_groupnames_cache(self) -> None:
        for line in self.lines:
            if ":" in line:
                u = line.split(":")[0]
                self._groupnames.add(u)

    def add_group(self, group_entry: config.GroupEntry) -> None:
        if group_entry.groupname in self._groupnames:
            return
        line = "{}\n".format(":".join(group_entry.group_fields()))
        self.lines.append(line)
        self._groupnames.add(group_entry.groupname)
