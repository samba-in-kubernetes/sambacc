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
import typing

from sambacc import config


class LoaderError(Exception):
    pass


def _utf8(s) -> bytes:
    return s.encode("utf8")


def template_config(
    fh: typing.IO, iconfig: config.InstanceConfig, enc=str
) -> None:
    fh.write(enc("[global]\n"))
    for gkey, gval in iconfig.global_options():
        fh.write(enc(f"\t{gkey} = {gval}\n"))

    for share in iconfig.shares():
        fh.write(enc("\n[{}]\n".format(share.name)))
        for skey, sval in share.share_options():
            fh.write(enc(f"\t{skey} = {sval}\n"))


class NetCmdLoader:
    cmd_prefix = ["net", "conf"]

    def _netcmd(self, *args, **kwargs):
        cmd = list(self.cmd_prefix)
        cmd.extend(args)
        return cmd, subprocess.Popen(cmd, **kwargs)

    def _check(self, cli, proc) -> None:
        ret = proc.wait()
        if ret != 0:
            raise LoaderError("failed to run {}".format(cli))

    def import_config(self, iconfig: config.InstanceConfig) -> None:
        """Import to entire instance config to samba config."""
        cli, proc = self._netcmd("import", "/dev/stdin", stdin=subprocess.PIPE)
        template_config(proc.stdin, iconfig, enc=_utf8)
        proc.stdin.close()
        self._check(cli, proc)

    def dump(self, out: typing.IO):
        """Dump the current smb config in an smb.conf format.
        Writes the dump to `out`.
        """
        cli, proc = self._netcmd("list", stdout=out)
        self._check(cli, proc)

    def _parse_shares(self, fh) -> typing.Iterable[str]:
        out = []
        for line in fh.readlines():
            line = line.strip().decode("utf8")
            if line == "global":
                continue
            out.append(line)
        return out

    def current_shares(self) -> typing.Iterable[str]:
        """Returns a list of current shares."""
        cli, proc = self._netcmd("listshares", stdout=subprocess.PIPE)
        # read and parse shares list
        try:
            shares = self._parse_shares(proc.stdout)
        finally:
            self._check(cli, proc)
        return shares

    def set(self, section: str, param: str, value: str) -> None:
        """Set an individual config parameter."""
        cli, proc = self._netcmd("setparm", section, param, value)
        self._check(cli, proc)
