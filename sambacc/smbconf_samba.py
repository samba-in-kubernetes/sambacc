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

import sys
import types
import importlib
import typing
import itertools

from sambacc.smbconf_api import ConfigStore


def _smbconf() -> types.ModuleType:
    return importlib.import_module("samba.smbconf")


def _s3smbconf() -> types.ModuleType:
    return importlib.import_module("samba.samba3.smbconf")


def _s3param() -> types.ModuleType:
    return importlib.import_module("samba.samba3.param")


if sys.version_info >= (3, 11):
    from typing import Self as _Self
else:
    _Self = typing.TypeVar("_Self", bound="SMBConf")


class SMBConf:
    """SMBConf wraps the samba smbconf library, supporting reading from and,
    when possible, writing to samba configuration backends.  The SMBConf type
    supports transactions using the context managager interface.  The SMBConf
    type can read and write configuration based on dictionary-like access,
    using shares as the keys. The global configuration is treated like a
    special "share".
    """

    def __init__(self, smbconf: typing.Any) -> None:
        self._smbconf = smbconf

    @classmethod
    def from_file(cls: typing.Type[_Self], path: str) -> _Self:
        """Open a smb.conf style configuration from the specified path."""
        return cls(_smbconf().init_txt(path))

    @classmethod
    def from_registry(
        cls: typing.Type[_Self],
        configfile: str = "/etc/samba/smb.conf",
        key: typing.Optional[str] = None,
    ) -> _Self:
        """Open samba's registry backend for configuration parameters."""
        s3_lp = _s3param().get_context()
        s3_lp.load(configfile)
        return cls(_s3smbconf().init_reg(key))

    @property
    def writeable(self) -> bool:
        """True if using a read-write backend."""
        return self._smbconf.is_writeable()

    # the extraneous `self: _Self` type makes mypy on python <3.11 happy.
    # otherwise it complains: `A function returning TypeVar should receive at
    # least one argument containing the same TypeVar`
    def __enter__(self: _Self) -> _Self:
        self._smbconf.transaction_start()
        return self

    def __exit__(
        self, exc_type: typing.Any, exc_value: typing.Any, tb: typing.Any
    ) -> None:
        if exc_type is None:
            self._smbconf.transaction_commit()
            return
        return self._smbconf.transaction_cancel()

    def __getitem__(self, name: str) -> list[tuple[str, str]]:
        try:
            n2, values = self._smbconf.get_share(name)
        except _smbconf().SMBConfError as err:
            if err.error_code == _smbconf().SBC_ERR_NO_SUCH_SERVICE:
                raise KeyError(name)
            raise
        if name != n2:
            raise ValueError(f"section name invalid: {name!r} != {n2!r}")
        return values

    def __setitem__(self, name: str, value: list[tuple[str, str]]) -> None:
        try:
            self._smbconf.delete_share(name)
        except _smbconf().SMBConfError as err:
            if err.error_code != _smbconf().SBC_ERR_NO_SUCH_SERVICE:
                raise
        self._smbconf.create_set_share(name, value)

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._smbconf.share_names())

    def import_smbconf(
        self, src: ConfigStore, batch_size: typing.Optional[int] = 100
    ) -> None:
        """Import content from one SMBConf configuration object into the
        current SMBConf configuration object.

        Set batch_size to the maximum number of "shares" to import in one
        transaction. Set batch_size to None to use only one transaction.
        """
        if not self.writeable:
            raise ValueError("SMBConf is not writable")
        if batch_size is None:
            return self._import_smbconf_all(src)
        return self._import_smbconf_batched(src, batch_size)

    def _import_smbconf_all(self, src: ConfigStore) -> None:
        with self:
            for sname in src:
                self[sname] = src[sname]

    def _import_smbconf_batched(
        self, src: ConfigStore, batch_size: int
    ) -> None:
        # based on a comment in samba's source code for the net command
        # only import N 'shares' at a time so that the transaction does
        # not exceed talloc memory limits
        def _batch_keyfunc(item: tuple[int, str]) -> int:
            return item[0] // batch_size

        for _, snames in itertools.groupby(enumerate(src), _batch_keyfunc):
            with self:
                for _, sname in snames:
                    self[sname] = src[sname]
