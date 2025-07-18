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
import enum
import errno
import json
import sys
import typing
import urllib

from .opener import Opener, FileOpener

_VALID_VERSIONS = ["v0"]

# alias open to _open to support test assertions when running
# as UID 0
_open = open

PasswdEntryTuple = typing.Tuple[str, str, str, str, str, str, str]
GroupEntryTuple = typing.Tuple[str, str, str, str]

# JSONData is not really a completely valid representation of json in
# the type system, but it's good enough for now. Using it can help
# clarify what works with json and what works with real python dicts.
JSONData = dict[str, typing.Any]

# the standard location for samba's smb.conf
SMB_CONF = "/etc/samba/smb.conf"
CLUSTER_META_JSON = "/var/lib/ctdb/shared/ctdb-nodes.json"
CTDB_NODES_PATH = "/var/lib/ctdb/shared/nodes"
CTDB_RECLOCK = "/var/lib/ctdb/shared/RECOVERY"

CTDB: typing.Final[str] = "ctdb"
ADDC: typing.Final[str] = "addc"
FEATURES: typing.Final[str] = "instance_features"

# cache for json schema data
_JSON_SCHEMA: dict[str, typing.Any] = {}


class ConfigFormat(enum.Enum):
    JSON = "json"
    TOML = "toml"
    YAML = "yaml"


class ValidationUnsupported(Exception):
    pass


class _FakeRefResolutionError(Exception):
    pass


class ConfigFormatUnsupported(Exception):
    pass


if sys.version_info >= (3, 11):

    def _load_toml(source: typing.IO) -> JSONData:
        try:
            import tomllib
        except ImportError:
            raise ConfigFormatUnsupported(ConfigFormat.TOML)
        return tomllib.load(source)

else:

    def _load_toml(source: typing.IO) -> JSONData:
        try:
            import tomli
        except ImportError:
            raise ConfigFormatUnsupported(ConfigFormat.TOML)
        if typing.TYPE_CHECKING:
            assert isinstance(source, typing.BinaryIO)
        return tomli.load(source)


def _load_yaml(source: typing.IO) -> JSONData:
    try:
        import yaml
    except ImportError:
        raise ConfigFormatUnsupported(ConfigFormat.YAML)
    return yaml.safe_load(source) or {}


def _detect_format(fname: str) -> ConfigFormat:
    if fname.endswith(".toml"):
        return ConfigFormat.TOML
    if fname.endswith((".yaml", ".yml")):
        return ConfigFormat.YAML
    return ConfigFormat.JSON


def _schema_validate(data: dict[str, typing.Any], version: str) -> None:
    try:
        import jsonschema  # type: ignore[import]
    except ImportError:
        raise ValidationUnsupported()
    try:
        _refreserror = getattr(jsonschema, "RefResolutionError")
    except AttributeError:
        _refreserror = _FakeRefResolutionError

    if version == "v0" and version not in _JSON_SCHEMA:
        try:
            import sambacc.schema.conf_v0_schema

            _JSON_SCHEMA[version] = sambacc.schema.conf_v0_schema.SCHEMA
        except ImportError:
            raise ValidationUnsupported()
    try:
        jsonschema.validate(instance=data, schema=_JSON_SCHEMA[version])
    except _refreserror:
        raise ValidationUnsupported()


def _check_config_version(data: JSONData) -> str:
    """Return the config data or raise a ValueError if the config
    is invalid or incomplete.
    """
    # short-cut to validate that this is something we want to consume
    version = data.get("samba-container-config")
    if version is None:
        raise ValueError("Invalid config: no samba-container-config key")
    elif version not in _VALID_VERSIONS:
        raise ValueError(f"Invalid config: unknown version {version}")
    return version


def _check_config_valid(
    data: JSONData, version: str, required: typing.Optional[bool] = None
) -> None:
    if required or required is None:
        try:
            _schema_validate(data, version)
        except ValidationUnsupported:
            if required:
                raise


def read_config_files(
    fnames: list[str],
    *,
    require_validation: typing.Optional[bool] = None,
    opener: typing.Optional[Opener] = None,
) -> GlobalConfig:
    """Read the global container config from the given filenames.
    At least one of the files from the fnames list must exist and contain
    a valid config. If none of the file names exist an error will be raised.
    """
    # NOTE: Right now if more than one config exists they'll be "merged" but
    # the merging is very simplistic right now. Mainly we expect that the
    # users will be split from the main config (for security reasons) but
    # it would be nicer to have a good merge algorithm handle everything
    # smarter at some point.
    opener = opener or FileOpener()
    gconfig = GlobalConfig()
    readfiles = set()
    for fname in fnames:
        config_format = _detect_format(str(fname))
        try:
            with opener.open(fname) as fh:
                gconfig.load(
                    fh,
                    require_validation=require_validation,
                    config_format=config_format,
                )
            readfiles.add(fname)
        except OSError as err:
            if getattr(err, "errno", 0) != errno.ENOENT:
                raise
    if not readfiles:
        # we read nothing! don't proceed
        raise ValueError(f"None of the config file paths exist: {fnames}")
    return gconfig


class SambaConfig(typing.Protocol):
    """Minimal samba configuration protocol."""

    def global_options(self) -> typing.Iterable[typing.Tuple[str, str]]:
        """Return global options for Samba."""
        ...  # pragma: no cover

    def shares(self) -> typing.Iterable[ShareConfig]:
        """Return share configurations for Samba."""
        ...  # pragma: no cover


class GlobalConfig:
    def __init__(
        self,
        source: typing.Optional[typing.IO] = None,
        *,
        initial_data: typing.Optional[JSONData] = None,
    ) -> None:
        self.data: JSONData = {} if initial_data is None else initial_data
        if source is not None:
            self.load(source)

    def load(
        self,
        source: typing.IO,
        *,
        require_validation: typing.Optional[bool] = None,
        config_format: typing.Optional[ConfigFormat] = None,
    ) -> None:
        config_format = config_format or ConfigFormat.JSON
        if config_format == ConfigFormat.TOML:
            data = _load_toml(source)
        elif config_format == ConfigFormat.YAML:
            data = _load_yaml(source)
        else:
            data = json.load(source)
        _check_config_valid(
            data, _check_config_version(data), require_validation
        )
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
        try:
            gnames = self.iconfig["globals"]
        except KeyError:
            # no globals section in the instance means no global options
            return
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
        includes = self.ctdb_config().get("conf_file_includes", [])
        return CTDBSambaConfig(includes=includes)

    def ctdb_config(self) -> JSONData:
        """Common configuration of CTDB itself."""
        if not self.with_ctdb:
            return {}
        ctdb = dict(self.gconfig.data.get("ctdb", {}))
        ctdb.setdefault("cluster_meta_uri", CLUSTER_META_JSON)
        ctdb.setdefault("nodes_path", CTDB_NODES_PATH)
        ctdb.setdefault("recovery_lock", CTDB_RECLOCK)
        ctdb.setdefault("log_level", "NOTICE")
        ctdb.setdefault("script_log_level", "ERROR")
        ctdb.setdefault("realtime_scheduling", "false")
        # this whole thing really needs to be turned into a real object type
        ctdb.setdefault("public_addresses", [])
        ctdb.setdefault("ctdb_port", 0)
        ctdb.setdefault("conf_file_includes", [])
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

    def organizational_units(self) -> typing.Iterable[OrganizationalUnitEntry]:
        if not self.with_addc:
            raise ValueError("ad dc not supported by configuration")
        ds_name: str = self.iconfig["domain_settings"]
        o_units = self.gconfig.data.get("organizational_units", {}).get(
            ds_name, []
        )
        for n, entry in enumerate(o_units):
            yield OrganizationalUnitEntry(self, entry, n)

    def keybridge_config(
        self, name: typing.Optional[str] = None
    ) -> typing.Optional[KeyBridgeConfig]:
        if not name:
            name = self.iconfig.get("keybridge_config")
        if not name:
            return None
        config = self.gconfig.data.get("keybridge", {}).get(name, {})
        return KeyBridgeConfig(config, name=name)

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
    def __init__(self, includes: typing.Optional[list[str]] = None) -> None:
        self._includes = includes

    def global_options(self) -> typing.Iterable[typing.Tuple[str, str]]:
        opts = [
            ("clustering", "yes"),
            ("ctdb:registry.tdb", "yes"),
        ]
        for include in self._includes or []:
            opts.append(("include", include))
        opts.append(("include", "registry"))
        return opts

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
        self.ou = grec.get("ou")
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
        self.interface_config = DCInterfaceConfig(drec.get("interfaces", {}))
        self.dcname = instance_name


class DCInterfaceConfig:
    def __init__(self, iface_config: dict) -> None:
        self.include_pattern: str = iface_config.get("include_pattern", "")
        self.exclude_pattern: str = iface_config.get("exclude_pattern", "")

    @property
    def configured(self) -> bool:
        """Return true if at least one interface property has been set."""
        return bool(self.include_pattern) or bool(self.exclude_pattern)


class DomainUserEntry(UserEntry):
    def __init__(self, iconf: InstanceConfig, urec: dict, num: int):
        super().__init__(iconf, urec, num)
        self.surname = urec.get("surname")
        self.given_name = urec.get("given_name")
        self.member_of = urec.get("member_of", [])
        self.ou = urec.get("ou")
        if not isinstance(self.member_of, list):
            raise ValueError("member_of should contain a list of group names")


class DomainGroupEntry(GroupEntry):
    pass


class OrganizationalUnitEntry:
    def __init__(self, iconf: InstanceConfig, urec: dict, num: int):
        self.iconfig = iconf
        self.ou_name = urec["name"]
        self.entry_num = num


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


class KeyBridgeScopeConfig:
    """Configuration of a single keybridge scope. Fields may or may not
    be populated depending on the type of scope.
    """

    def __init__(self, scope_cfg: dict) -> None:
        self._cfg = scope_cfg

    @property
    def name(self) -> str:
        return str(self._cfg.get("name", ""))

    @property
    def type_name(self) -> str:
        return self.name.split(".")[0]

    @property
    def subname(self) -> str:
        return self.name.split(".", 1)[-1]

    @property
    def hostnames(self) -> list[str]:
        return list(self._cfg.get("hostnames", []))

    @property
    def host_ports(self) -> list[tuple[str, int]]:
        default_port = self.port
        out: list[tuple[str, int]] = []
        for host in self.hostnames:
            host, port = _safe_split_host_port(host)
            if port <= 0 and default_port <= 0:
                raise ValueError("no host port and no default port")
            elif port <= 0:
                out.append((host, default_port))
            else:
                out.append((host, int(port)))
        return out

    @property
    def port(self) -> int:
        return int(self._cfg.get("port", -1))

    @property
    def tls_paths(self) -> dict[str, str]:
        _tls_paths = self._cfg.get("tls_paths", {})
        if not _tls_paths:
            return {}
        # ensure dict keys are consistent and nothing extra
        return {
            "cert": str(_tls_paths.get("cert", "")),
            "key": str(_tls_paths.get("key", "")),
            "ca_cert": str(_tls_paths.get("ca_cert", "")),
        }


class KeyBridgeVerifyConfig:
    """Configuration for keybridge peer verification. Each check_*
    value can be missing - and not checked - or a range of ints or
    a list ints.
    """

    def __init__(self, verify_cfg: dict) -> None:
        self._cfg = verify_cfg

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._cfg!r})"

    @property
    def check_pid(self) -> typing.Union[None, range, typing.Collection[int]]:
        return self.parameter(self._cfg.get("check_pid"))

    @property
    def check_uid(self) -> typing.Union[None, range, typing.Collection[int]]:
        return self.parameter(self._cfg.get("check_uid"))

    @property
    def check_gid(self) -> typing.Union[None, range, typing.Collection[int]]:
        return self.parameter(self._cfg.get("check_gid"))

    @classmethod
    def parameter(
        cls,
        value: typing.Optional[str],
    ) -> typing.Union[None, range, typing.Collection[int]]:
        """Convert a value into a PID/UID/GID range or collection.
        Formats are:
          <num>: a single int to match
          <num>-<num>: a range of values
          <num>+: a range of values ending at a 32 bit max
          <num>[,<num>][,<num>...]: a list of allowed ints
        """
        if value is None:
            return None

        if value.endswith("+"):
            value = value[:-1]
            if value.isdigit():
                # allow any 32 bit int over value
                return range(int(value), 1 << 32)

        if "-" in value:
            parts = value.split("-", 1)
            if len(parts) != 2:
                raise ValueError("ranges must take the form <int>-<int>")
            if parts[0].isdigit() and parts[1].isdigit():
                return range(int(parts[0]), int(parts[1]))
            raise ValueError("ranges must start and end with integers")

        if "," in value:
            parts = value.split(",")
            if not all(s.isdigit() for s in parts):
                ValueError("lists must contain only integers")
            return set(int(s) for s in parts)

        if value.isdigit():
            return {int(value)}

        raise ValueError("not a valid check value")


class KeyBridgeConfig:
    """Return a keybridge server configuration object.
    A configuration consists of zero or more scopes and an optional
    peer verification config.
    """

    def __init__(self, kbconf: dict, name: str = "") -> None:
        self._kbconf = kbconf
        self._name = name

    def scopes(self) -> list[KeyBridgeScopeConfig]:
        """Return a list of scope configuration objects."""
        _scopes = self._kbconf.get("scopes", [])
        return [KeyBridgeScopeConfig(s) for s in _scopes]

    def verify(self) -> typing.Optional[KeyBridgeVerifyConfig]:
        """Return a configuration for a general peer verification wrapper."""
        _verify = self._kbconf.get("verify_peer")
        if not _verify:
            return None
        return KeyBridgeVerifyConfig(_verify)

    def update_mem_scope(self) -> None:
        """Create or update a mem scope in this configuration."""
        if "mem" in {s.type_name for s in self.scopes()}:
            return
        self._kbconf.setdefault("scopes", []).append({"name": "mem"})

    def update_kmip_scope(
        self,
        hostnames: typing.Optional[list[str]] = None,
        port: typing.Optional[int] = None,
        tls_cert: typing.Optional[str] = None,
        tls_key: typing.Optional[str] = None,
        tls_ca_cert: typing.Optional[str] = None,
        subname: str = "1",
    ) -> None:
        """Create or update a kmip scope in this configuration.  If the kmip
        scope already exists any non-None argument to this function will update
        the corresponding configuration value in the matching scope.
        """
        _scopes = {s.type_name: s._cfg for s in self.scopes()}
        if "kmip" in _scopes:
            scope = _scopes["kmip"]
        else:
            scope = {"name": f"kmip.{subname}"}
            self._kbconf.setdefault("scopes", []).append(scope)
        if hostnames:
            scope["hostnames"] = hostnames
        if port and port > 0:
            scope["port"] = port
        _tls = (tls_cert, tls_key, tls_ca_cert)
        if any(_tls) and not all(_tls):
            raise ValueError("specify all TLS files or none")
        elif all(_tls):
            scope["tls_paths"] = {
                "cert": tls_cert,
                "key": tls_key,
                "ca_cert": tls_ca_cert,
            }


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


def _safe_split_host_port(host: str, scheme: str = "https") -> tuple[str, int]:
    if host.count(":") > 1 and "[" not in host:
        # assume this is an undecorated ipv6 and pass it thru w/o port
        return (host, -1)
    # otherwise let urllib do the work for us
    parsed = urllib.parse.urlparse(f"{scheme}://{host}")
    assert parsed.hostname, "invalid hostname"  # should be impossible
    return parsed.hostname, int(parsed.port or -1)
