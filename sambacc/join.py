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

import subprocess


class JoinError(Exception):
    pass


def _utf8(s):
    return s.encode("utf8")


class Joiner:
    cmd_prefix = ["net", "ads"]

    def _netcmd(self, *args, **kwargs):
        cmd = list(self.cmd_prefix)
        cmd.extend(args)
        return cmd, subprocess.Popen(cmd, **kwargs)

    def join(self, username, password, dns_updates=False):
        args = []
        if not dns_updates:
            args.append("--no-dns-updates")
        args.extend(["-U", username])

        cli, proc = self._netcmd("join", *args, stdin=subprocess.PIPE)
        proc.stdin.write(_utf8(password))
        proc.stdin.write(b"\n")
        proc.stdin.close()
        ret = proc.wait()
        if ret != 0:
            raise JoinError("failed to run {}".format(cli))
