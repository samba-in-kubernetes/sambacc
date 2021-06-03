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

import binascii
import errno
import json
import typing

_VALID_VERSIONS = ["v0"]

# alias open to _open to support test assertions when running
# as UID 0
_open = open

PasswdEntryTuple = typing.Tuple[str, str, str, str, str, str, str]
GroupEntryTuple = typing.Tuple[str, str, str, str]

# the standard location for samba's smb.conf
SMB_CONF = "/etc/samba/smb.conf"

CTDB = "ctdb"
FEATURES = "instance_features"


def read_config_files(fnames) -> GlobalConfig:
    """Read the global container config from the given filenames.
    At least one of the files from the fnames list must exist and contain
    a valid config. If none of the file names exist an error will be raised.
    """
    # NOTE: Right now if more than one config exists they'll be "merged" but
    # the merging is very simplistic right now. Mainly we expect that the
    # users will be split from the main config (for security reasons) but
    # it would be nicer to have a good merge algorithm handle everything
    # smarter at some point.
    gconfig = GlobalConfig()
    readfiles = set()
    for fname in fnames:
        try:
            with _open(fname) as fh:
                gconfig.load(fh)
            readfiles.add(fname)
        except OSError as err:
            if getattr(err, "errno", 0) != errno.ENOENT:
                raise
    if not readfiles:
        # we read nothing! don't proceed
        raise ValueError(f"None of the config file paths exist: {fnames}")
    # Verify that we loaded something
    check_config_data(gconfig.data)
    return gconfig


def check_config_data(data) -> dict:
    """Return the config data or raise a ValueError if the config
    is invalid or incomplete.
    """
    # short-cut to validate that this is something we want to consume
    version = data.get("samba-container-config")
    if version is None:
        raise ValueError("Invalid config: no samba-container-config key")
    elif version not in _VALID_VERSIONS:
        raise ValueError(f"Invalid config: unknown version {version}")
    return data


class SambaConfig(typing.Protocol):
    def global_options(self) -> typing.Iterable[typing.Tuple[str, str]]:
        ...

    def shares(self) -> typing.Iterable[ShareConfig]:
        ...


class GlobalConfig:
    def __init__(self, source=None):
        self.data = {}
        if source is not None:
            self.load(source)

    def load(self, source: typing.IO) -> None:
        data = check_config_data(json.load(source))
        self.data.update(data)

    def get(self, ident: str) -> InstanceConfig:
        iconfig = self.data["configs"][ident]
        return InstanceConfig(self, iconfig)


class InstanceConfig:
    def __init__(self, conf: GlobalConfig, iconfig: dict):
        self.gconfig = conf
        self.iconfig = iconfig

    def global_options(self) -> typing.Iterable[typing.Tuple[str, str]]:
        """Iterate over global options."""
        # Pull in all global sections that apply
        gnames = self.iconfig["globals"]
        for gname in gnames:
            global_section = self.gconfig.data["globals"][gname]
            for k, v in global_section.get("options", {}).items():
                yield k, v
        # Special, per-instance settings
        instance_name = self.iconfig.get("instance_name", None)
        if instance_name:
            yield "netbios name", instance_name

    def uid_base(self) -> int:
        return 1000

    def gid_base(self) -> int:
        return 1000

    def shares(self) -> typing.Iterable[ShareConfig]:
        """Iterate over share configs."""
        for sname in self.iconfig.get("shares", []):
            yield ShareConfig(self.gconfig, sname)

    def users(self) -> typing.Iterable[UserEntry]:
        all_users = self.gconfig.data.get("users", {}).get("all_entries", {})
        for n, entry in enumerate(all_users):
            yield UserEntry(self, entry, n)

    def groups(self) -> typing.Iterable[GroupEntry]:
        user_gids = {u.gid: u for u in self.users()}
        all_groups = self.gconfig.data.get("groups", {}).get("all_entries", {})
        for n, entry in enumerate(all_groups):
            ge = GroupEntry(self, entry, n)
            if ge.gid in user_gids:
                del user_gids[ge.gid]
            yield ge
        for uentry in user_gids.values():
            yield uentry.vgroup()

    @property
    def with_ctdb(self):
        return CTDB in self.iconfig.get(FEATURES, [])

    def ctdb_smb_config(self) -> CTDBSambaConfig:
        if not self.with_ctdb:
            raise ValueError("ctdb not supported in configuration")
        return CTDBSambaConfig()


class CTDBSambaConfig:
    def global_options(self) -> typing.Iterable[typing.Tuple[str, str]]:
        return [
            ("clustering", "yes"),
            ("ctdb:registry.tdb", "yes"),
            ("include", "registry"),
        ]

    def shares(self) -> typing.Iterable[ShareConfig]:
        return []


class ShareConfig:
    def __init__(self, conf, sharename):
        self.gconfig = conf
        self.name = sharename

    def share_options(self) -> typing.Iterable[typing.Tuple[str, str]]:
        """Iterate over share options."""
        share_section = self.gconfig.data["shares"][self.name]
        return iter(share_section.get("options", {}).items())


class UserEntry:
    def __init__(self, iconf: InstanceConfig, urec: dict, num: int):
        self.iconfig = iconf
        self.username = urec["name"]
        self.entry_num = num
        self._uid = urec.get("uid")
        self._gid = urec.get("gid")
        self._nt_passwd = str(urec.get("nt_hash", ""))
        self._plaintext_passwd = str(urec.get("password", ""))
        if self._uid is not None:
            if not isinstance(self._uid, int):
                raise ValueError("invalid uid value")
        if self._gid is not None:
            if not isinstance(self._gid, int):
                raise ValueError("invalid gid value")

    @property
    def uid(self) -> int:
        if self._uid:
            return self._uid
        return self.iconfig.uid_base() + self.entry_num

    @property
    def gid(self) -> int:
        if self._gid:
            return self._gid
        return self.iconfig.gid_base() + self.entry_num

    @property
    def dir(self) -> str:
        return "/invalid"

    @property
    def shell(self) -> str:
        return "/bin/false"

    @property
    def nt_passwd(self) -> bytes:
        # the json will store the hash as a hex encoded string
        return binascii.unhexlify(self._nt_passwd)

    @property
    def plaintext_passwd(self) -> str:
        return self._plaintext_passwd

    def passwd_fields(self) -> PasswdEntryTuple:
        # fields: name, passwd, uid, gid, GECOS, dir, shell
        return (
            self.username,
            "x",
            str(self.uid),
            str(self.gid),
            "",
            self.dir,
            self.shell,
        )

    def vgroup(self) -> GroupEntry:
        """In case there is no explicit group for the specified user. This
        handy method makes a "virtual" group based on the user info.
        """
        return GroupEntry(
            self.iconfig, dict(name=self.username, gid=self.gid), 0
        )


class GroupEntry:
    def __init__(self, iconf: InstanceConfig, grec: dict, num: int):
        self.iconfig = iconf
        self.groupname = grec["name"]
        self.entry_num = num
        self._gid = grec.get("gid")
        if self._gid is not None:
            if not isinstance(self._gid, int):
                raise ValueError("invalid gid value")

    @property
    def gid(self) -> int:
        if self._gid:
            return self._gid
        return self.iconfig.gid_base() + self.entry_num

    def group_fields(self) -> GroupEntryTuple:
        # fields: name, passwd, gid, members(comma separated)
        return (self.groupname, "x", str(self.gid), "")
