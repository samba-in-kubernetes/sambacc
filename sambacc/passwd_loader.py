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


class LineFileLoader:
    def __init__(self, path):
        self.path = path
        self.lines = []

    def read(self):
        with open(self.path) as f:
            self.readfp(f)

    def write(self):
        tpath = self._tmp_path(self.path)
        with open(tpath, "w") as f:
            self.writefp(f)
        os.rename(tpath, self.path)

    def _tmp_path(self, path):
        # for later: make this smarter
        return f"{path}.tmp"

    def readfp(self, fp):
        self.loadlines(fp.readlines())

    def writefp(self, fp):
        for line in self.dumplines():
            fp.write(line)
        fp.flush()

    def loadlines(self, lines):
        """Load in the lines from the text source.
        """
        for line in lines:
            self.lines.append(line)

    def dumplines(self):
        """Dump the file content as lines of text.
        """
        prev = None
        for line in self.lines:
            if prev and not prev.endswith("\n"):
                yield "\n"
            yield line
            prev = line


class PasswdFileLoader(LineFileLoader):
    def __init__(self, path="/etc/passwd"):
        super().__init__(path)
        self._usernames = set()

    def readfp(self, fp):
        super().readfp(fp)
        self._update_usernames_cache()

    def _update_usernames_cache(self):
        for line in self.lines:
            if ":" in line:
                u = line.split(":")[0]
                self._usernames.add(u)

    def add_user(self, user_entry):
        if user_entry.username in self._usernames:
            return
        line = "{}\n".format(":".join(user_entry.passwd_fields()))
        self.lines.append(line)
        self._usernames.add(user_entry.username)


class GroupFileLoader(LineFileLoader):
    def __init__(self, path="/etc/group"):
        super().__init__(path)
        self._groupnames = set()

    def readfp(self, fp):
        super().readfp(fp)
        self._update_groupnames_cache()

    def _update_groupnames_cache(self):
        for line in self.lines:
            if ":" in line:
                u = line.split(":")[0]
                self._groupnames.add(u)

    def add_group(self, group_entry):
        if group_entry.groupname in self._groupnames:
            return
        line = "{}\n".format(":".join(group_entry.group_fields()))
        self.lines.append(line)
        self._groupnames.add(group_entry.groupname)
