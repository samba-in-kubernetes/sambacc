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


class ConfigStore(typing.Protocol):
    def __getitem__(self, name: str) -> list[tuple[str, str]]:
        """Get an item, returning a config section."""
        ...  # pragma: no cover

    def __setitem__(self, name: str, value: list[tuple[str, str]]) -> None:
        """Set a new config section."""
        ...  # pragma: no cover

    def __iter__(self) -> typing.Iterator[str]:
        """Iterate over config sections in the store."""
        ...  # pragma: no cover


class SimpleConfigStore:
    def __init__(self) -> None:
        self._data: dict[str, list[tuple[str, str]]] = {}

    @property
    def writeable(self) -> bool:
        """True if using a read-write backend."""
        return True

    def __getitem__(self, name: str) -> list[tuple[str, str]]:
        return self._data[name]

    def __setitem__(self, name: str, value: list[tuple[str, str]]) -> None:
        self._data[name] = value

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._data.keys())

    def import_smbconf(
        self, src: ConfigStore, batch_size: typing.Optional[int] = None
    ) -> None:
        """Import content from one SMBConf configuration object into the
        current SMBConf configuration object.

        batch_size is ignored.
        """
        for sname in src:
            self[sname] = src[sname]


def write_store_as_smb_conf(out: typing.IO, conf: ConfigStore) -> None:
    """Write the configuration store in smb.conf format to `out`."""
    # unfortunately, AFAIK, there's no way for an smbconf to write
    # into a an smb.conf/ini style file. We have to do it on our own.
    # ---
    # Make sure global section comes first.
    sections = sorted(conf, key=lambda v: 0 if v == "global" else 1)
    for sname in sections:
        out.write(str("\n[{}]\n".format(sname)))
        for skey, sval in conf[sname]:
            out.write(str(f"\t{skey} = {sval}\n"))
