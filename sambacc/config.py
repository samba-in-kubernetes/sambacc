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

CTDB: typing.Final[str] = "ctdb"
ADDC: typing.Final[str] = "addc"
FEATURES: typing.Final[str] = "instance_features"


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
        ...  # pragma: no cover

    def shares(self) -> typing.Iterable[ShareConfig]:
        ...  # pragma: no cover


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
            yield ShareConfig(self.gconfig, sname, iconfig=self.iconfig)

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
    def with_ctdb(self) -> bool:
        return CTDB in self.iconfig.get(FEATURES, [])

    @property
    def with_addc(self) -> bool:
        return ADDC in self.iconfig.get(FEATURES, [])

    def ctdb_smb_config(self) -> CTDBSambaConfig:
        if not self.with_ctdb:
            raise ValueError("ctdb not supported in configuration")
        return CTDBSambaConfig()

    def ctdb_config(self) -> typing.Dict[str, str]:
        """Common configuration of CTDB itself."""
        if not self.with_ctdb:
            return {}
        ctdb = dict(self.gconfig.data.get("ctdb", {}))
        ctdb.setdefault("nodes_json", "/var/lib/ctdb/shared/ctdb-nodes.json")
        ctdb.setdefault("nodes_path", "/var/lib/ctdb/shared/nodes")
        ctdb.setdefault("recovery_lock", "/var/lib/ctdb/shared/RECOVERY")
        ctdb.setdefault("log_level", "DEBUG")
        ctdb.setdefault("script_log_level", "DEBUG")
        ctdb.setdefault("realtime_scheduling", "false")
        return ctdb

    def domain(self) -> DomainConfig:
        """Return the general domain settings for this DC instance."""
        if not self.with_addc:
            raise ValueError("ad dc not supported by configuration")
        domains = self.gconfig.data.get("domain_settings", {})
        instance_name: str = self.iconfig.get("instance_name", "")
        return DomainConfig(
            drec=domains[self.iconfig["domain_settings"]],
            instance_name=instance_name,
        )

    def domain_users(self) -> typing.Iterable[DomainUserEntry]:
        if not self.with_addc:
            raise ValueError("ad dc not supported by configuration")
        ds_name: str = self.iconfig["domain_settings"]
        dusers = self.gconfig.data.get("domain_users", {}).get(ds_name, [])
        for n, entry in enumerate(dusers):
            yield DomainUserEntry(self, entry, n)

    def domain_groups(self) -> typing.Iterable[DomainGroupEntry]:
        if not self.with_addc:
            raise ValueError("ad dc not supported by configuration")
        ds_name: str = self.iconfig["domain_settings"]
        dgroups = self.gconfig.data.get("domain_groups", {}).get(ds_name, [])
        for n, entry in enumerate(dgroups):
            yield DomainGroupEntry(self, entry, n)

    def __eq__(self, other: typing.Any) -> bool:
        if isinstance(other, InstanceConfig) and self.iconfig == other.iconfig:
            self_shares = _shares_data(self.gconfig, self.iconfig)
            other_shares = _shares_data(other.gconfig, other.iconfig)
            self_globals = _globals_data(self.gconfig, self.iconfig)
            other_globals = _globals_data(other.gconfig, other.iconfig)
            return (
                self_shares == other_shares and self_globals == other_globals
            )
        return False


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
    def __init__(
        self,
        conf: GlobalConfig,
        sharename: str,
        iconfig: typing.Optional[dict] = None,
    ) -> None:
        self.gconfig = conf
        self.name = sharename
        self.iconfig = iconfig or {}

    def share_options(self) -> typing.Iterable[typing.Tuple[str, str]]:
        """Iterate over share options."""
        share_section = self.gconfig.data["shares"][self.name]
        return iter(share_section.get("options", {}).items())

    def path(self) -> typing.Optional[str]:
        """Return the path value from the smb.conf options."""
        share_section = self.gconfig.data["shares"][self.name]
        try:
            return share_section["options"]["path"]
        except KeyError:
            return None

    def permissions_config(self) -> PermissionsConfig:
        """Return a permissions configuration for the share."""
        # each share can have it's own permissions config,
        # but if it does not it will default to the instance's
        # config
        try:
            share_perms = self.gconfig.data["shares"][self.name]["permissions"]
            return PermissionsConfig(share_perms)
        except KeyError:
            pass
        try:
            instance_perms = self.iconfig["permissions"]
            return PermissionsConfig(instance_perms)
        except KeyError:
            pass
        # use the internal defaults
        return PermissionsConfig({})


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


class DomainConfig:
    def __init__(self, drec: dict, instance_name: str):
        self.realm = drec["realm"]
        self.short_domain = drec.get("short_domain", "")
        self.admin_password = drec.get("admin_password", "")
        self.dcname = instance_name


class DomainUserEntry(UserEntry):
    def __init__(self, iconf: InstanceConfig, urec: dict, num: int):
        super().__init__(iconf, urec, num)
        self.surname = urec.get("surname")
        self.given_name = urec.get("given_name")
        self.member_of = urec.get("member_of", [])
        if not isinstance(self.member_of, list):
            raise ValueError("member_of should contain a list of group names")


class DomainGroupEntry(GroupEntry):
    pass


class PermissionsConfig:
    _method_key: str = "method"
    _status_xattr_key: str = "status_xattr"
    _default_method: str = "none"
    _default_status_xattr: str = "user.share-perms-status"

    def __init__(self, pconf: dict[str, str]) -> None:
        self._pconf = pconf
        self.method: str = pconf.get(self._method_key, self._default_method)
        self.status_xattr: str = pconf.get(
            self._status_xattr_key, self._default_status_xattr
        )

    @property
    def options(self) -> dict[str, str]:
        filter_keys = {self._method_key, self._status_xattr_key}
        return {k: v for k, v in self._pconf.items() if k not in filter_keys}


def _shares_data(gconfig: GlobalConfig, iconfig: dict) -> list:
    try:
        shares = iconfig["shares"]
    except KeyError:
        return []
    return [gconfig.data["shares"][n] for n in shares]


def _globals_data(gconfig: GlobalConfig, iconfig: dict) -> list:
    try:
        gnames = iconfig["globals"]
    except KeyError:
        return []
    return [gconfig.data["globals"][n] for n in gnames]
