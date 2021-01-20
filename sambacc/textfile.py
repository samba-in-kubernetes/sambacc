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


class TextFileLoader:
    def __init__(self, path):
        self.path = path

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
