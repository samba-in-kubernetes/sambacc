#
# sambacc: a samba container configuration tool
# Copyright (C) 2026  John Mulligan
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

"""Read (MIT) Kerberos krb5.conf style configuration.

The krb5.conf format is similar to INI style. But with unique extensions.

The ``include``, ``includedir`` and ``module`` directives are recognized but
not followed by the file parser.

configparser is not used as it can not handle the nested groups and include
directives that are present in the krb5 config files we expect to parse.
"""

from collections.abc import Iterable, Iterator
import logging
import pathlib
import re
import typing

from .textfile import TextFileLoader
from .typelets import Self

_logger = logging.getLogger(__name__)

KRB5_CONF = "/etc/krb5.conf"
KRB5_CONF_DIR = "/etc/krb5.conf.d"

_SECTION_RE = re.compile(r"^\[\s*([^\]\s][^\]]*?)\s*\]")
_KV_RE = re.compile(r"^(\S.*?)\s*=\s*(.*)$")
_DIRECTIVES = ("include", "includedir")
_PLUGINS = "plugins"
_MODULE = "module"
# Names of files in a config directory that the MIT library will read.
_DIR_FILE_RE = re.compile(r"^[A-Za-z0-9_-]+$|\.conf$")
_INDENT = 4


class KrbConfError(ValueError):
    """Raised when krb5.conf content can not be parsed."""


type Value = str | Group
type KeyValue = tuple[str, Value]


class TooManyKeys(KeyError):
    pass


class Group:
    """An ordered group of items: a section or a nested "{ }" group.

    Keys may repeat so items are held as a list of (key, value) pairs.
    """

    def __init__(self, items: list[KeyValue]) -> None:
        self.items: list[KeyValue] = items

    @classmethod
    def empty(cls) -> Self:
        """Return an empty Group."""
        return cls([])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Group):
            return NotImplemented
        return self.items == other.items

    def __repr__(self) -> str:
        return f"Group({self.items!r})"

    def add(self, key: str, value: Value) -> None:
        self.items.append((key, value))

    def extend(self, other: "Group") -> None:
        self.items.extend(other.items)

    def __iter__(self) -> Iterator[KeyValue]:
        return iter(self.items)

    def get(self, key: str, default: Value | None = None) -> Value | None:
        """Get a single value from the group. Raises TooManyKeys if there
        are multiple matching keys in the group.
        Return default if no value found for given key.
        """
        results = self.get_all(key)
        rcount = len(results)
        if rcount > 1:
            raise TooManyKeys(key)
        if rcount < 1:
            return default
        _, value = results[0]
        return value

    def get_all(self, key: str) -> list[KeyValue]:
        """Return a list of all KeyValue pairs matching the provided key."""
        return [kv for kv in self.items if key == kv[0]]


type _NLine = tuple[int, str]


def _is_directive(line: str, section: str) -> bool:
    _directives = set(_DIRECTIVES)
    if section == _PLUGINS:
        # do not mistake a module key outside of plugins section as a
        # directive. this does NOT mean we properly handle module directives
        # for plugins. for now we choose not to for simplicity
        _directives.add(_MODULE)
    return line.split(None, 1)[0] in _directives


class KrbConfLoader(TextFileLoader):
    """A single krb5.conf style file."""

    def __init__(self, path: str):
        super().__init__(path)
        self.sections: dict[str, Group] = {}
        self.directives: dict[tuple[str, int], tuple[str, str]] = {}

    def loadlines(self, lines: Iterable[str]) -> None:
        """Parse lines of text."""
        stripped = ((i, ln.strip()) for (i, ln) in enumerate(lines, 1))
        filtered = (
            (i, ln) for (i, ln) in stripped if ln and ln[0] not in "#;"
        )
        self._parse_new(filtered)

    def _parse_new(self, lines: Iterable[_NLine]) -> None:
        section = ""
        for lnum, line in lines:
            if match := _SECTION_RE.match(line):
                section = match.group(1)
                group = Group.empty()
                self.sections.setdefault(section, group)
            elif _is_directive(line, section):
                self._parse_directive(lnum, line)
                _logger.debug("ignoring directive: %s", line)
            elif line == "}":
                self._error(lnum, "unmatched '}'")
            elif not section:
                self._error(lnum, "content outside of a section")
            else:
                self._parse_kv(
                    lines, section, self.sections[section], lnum, line
                )

    def _parse_kv(
        self,
        lines: Iterable[_NLine],
        section: str,
        dest: Group,
        lnum: int,
        line: str,
    ) -> None:
        match = _KV_RE.match(line)
        if not match:
            self._error(lnum, f"invalid line: {line!r}")
            return  # mypy needs this
        key = match.group(1)
        value = match.group(2).strip()
        if value != "{":
            dest.add(key, _unquote(value))
            return
        inner_group = Group.empty()
        self._parse_group(lines, lnum, section, inner_group)
        dest.add(key, inner_group)

    def _parse_group(
        self,
        lines: Iterable[_NLine],
        start: int,
        section: str,
        dest: Group,
    ) -> None:
        """Parse lines into `group` up to its closing "}"."""
        for lnum, line in lines:
            if line == "}":
                return
            if _is_directive(line, section):
                self._error(lnum, f"unexpected directive inside block: {line}")
            self._parse_kv(lines, section, dest, lnum, line)
        self._error(start, "unterminated '{' group")

    def _parse_directive(self, lnum: int, line: str) -> None:
        # directives are typically only going to be in the main krb5.conf
        # but we don't care to enforce that at this time
        values = line.split(None, 1)
        assert len(values) == 2
        key = (self.path, lnum)
        self.directives[key] = typing.cast(tuple[str, str], tuple(values))

    def _error(self, lnum: int, msg: str) -> KrbConfError:
        raise KrbConfError(f"error parsing {self.path}:{lnum}: {msg}")

    def dumplines(self) -> Iterable[str]:
        if self.directives:
            raise KrbConfError("can not dump a conf with directives")
        for section, group in self.sections.items():
            yield f"[{section}]\n"
            yield from self._dump_pairs(group, indent=_INDENT)
            yield "\n"

    def _dump_pairs(self, group: Group, indent: int) -> Iterable[str]:
        _indent = " " * indent
        for key, value in group:
            if isinstance(value, str):
                yield f"{_indent}{key} = {value}\n"
            else:
                yield f"{_indent}{key} = {{\n"
                yield from self._dump_pairs(value, indent + _INDENT)
                yield f"{_indent}}}\n"

    def has_directive(self, directive: str, value: str | None) -> bool:
        """Check for a directive. If value is None check that any
        directive type is given. If value is a string check that
        a matching directive exists.
        """
        if value is None:
            return directive in {dk for dk, _ in self.directives.values()}
        return (directive, value) in self.directives.values()


class KrbConf:
    """The combined content of krb5.conf and the files in its config dir."""

    def __init__(self) -> None:
        self.sources: dict[pathlib.Path, KrbConfLoader] = {}

    def add(self, path: pathlib.Path, kconf: KrbConfLoader) -> None:
        self.sources[path] = kconf

    def __getitem__(self, name: str | pathlib.Path) -> KrbConfLoader:
        return self.sources[pathlib.Path(name)]

    def find(self, name: str) -> tuple[pathlib.Path, KrbConfLoader] | None:
        for path in self.sources:
            if path.name == name:
                return path, self.sources[path]
        return None

    def merged(self) -> KrbConfLoader:
        """Return a KrbConfLoader with all conf file contents merged."""
        merged_conf = KrbConfLoader("<virtual>")
        for src_conf in self.sources.values():
            for section, sg in src_conf.sections.items():
                dg = merged_conf.sections.setdefault(section, Group.empty())
                dg.extend(sg)
            for key, directive in src_conf.directives.items():
                merged_conf.directives[key] = directive
        return merged_conf


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def default_krb5_conf() -> pathlib.Path:
    """Return a Path object for the default krb5.conf path."""
    return pathlib.Path(KRB5_CONF)


def conf_dir_files(
    path: str | pathlib.Path = KRB5_CONF_DIR,
) -> list[pathlib.Path]:
    """Return the paths of the config files in a krb5.conf config directory.

    Like the MIT library, only names ending in ".conf" or made up solely of
    letters, digits, '-' and '_' are used. Results are in sorted order. A
    missing directory is treated as empty. Ignores dotfiles.
    """
    try:
        paths = sorted(pathlib.Path(path).iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return []
    return [
        p
        for p in paths
        if not p.name.startswith(".")
        and _DIR_FILE_RE.search(p.name)
        and p.is_file()
    ]


def load(
    paths: list[pathlib.Path],
    ignore_missing: bool = False,
) -> KrbConf:
    """Load krb5.conf-style files."""
    conf = KrbConf()
    for p in paths:
        kfile = KrbConfLoader(str(p))
        try:
            kfile.read()
        except FileNotFoundError:
            if ignore_missing:
                _logger.warning("krb5 config file not found: %s", p)
                continue
            raise
        conf.add(p, kfile)
    return conf


class _Status:
    def __init__(self, reason: str) -> None:
        self.reason = reason


class _Failure(_Status):
    pass


class _Ignore(_Status):
    pass


def _check_files(krb_config: KrbConf) -> _Status | None:
    pth_kc = krb_config.find("krb5.conf")
    if not pth_kc:
        return _Ignore("no krb5.conf found")
    kc = pth_kc[1]
    valid_dirs = {KRB5_CONF_DIR, f"{KRB5_CONF_DIR}/"}
    if not any(
        dname == "includedir" and dval in valid_dirs
        for dname, dval in kc.directives.values()
    ):
        return _Failure("no krb5.conf includedir found")
    for src in krb_config.sources.values():
        for dname, dval in src.directives.values():
            if dname == "include" or (
                dname == "includedir"
                and (src is not kc or dval not in valid_dirs)
            ):
                return _Failure("unexpected include directive found")
    return None


def _check_content(krb_config: KrbConf) -> _Status | None:
    merged = krb_config.merged()
    if merged.has_directive("module", None):
        return _Failure("krb5 config has unsupported module directive")
    merged_libdefaults = merged.sections.get("libdefaults")
    if not merged_libdefaults:
        return _Failure("no libdefaults section found")
    try:
        enctypes = merged_libdefaults.get("permitted_enctypes")
    except TooManyKeys:
        return _Failure("too many keys found for permitted_enctypes")
    if not enctypes:
        return _Failure("no permitted_enctypes key found")
    if not isinstance(enctypes, str):
        return _Failure("permitted_enctypes is not a string value")
    return None


def _update_algos(krb_config: KrbConf) -> _Status | None:
    if not (pcc := krb_config.find("crypto-policies")):
        return _Ignore("no crypto-policies file found")
    cp_path, cp_conf = pcc
    if list(cp_conf.sections.keys()) != ["libdefaults"]:
        return _Failure(
            "crypto-policies must contain only libdefaults section"
        )
    libdefaults = cp_conf.sections["libdefaults"]
    if [k for k, _ in libdefaults.items] != ["permitted_enctypes"]:
        return _Failure(
            "crypto-policies libdefaults must contain only permitted_enctypes"
        )
    enctypes = libdefaults.items[0][1]
    if not isinstance(enctypes, str):
        return _Failure("permitted_enctypes is not a string value")
    enclist = enctypes.split()
    missing = False
    for alg in ("aes256-cts-hmac-sha1-96", "aes128-cts-hmac-sha1-96"):
        if alg not in enclist:
            enctypes = f"{enctypes} {alg}"
            missing = True
    if not missing:
        return _Ignore("ad support algorithms found")
    _logger.info("Updating kerberos config: %s", cp_path)
    # all these files in the wild should just have the one permitted_enctypes
    # line. we're adding in missing required enctypes so we can reset the
    # whole config file contents to permitted_enctypes
    libdefaults.items = [("permitted_enctypes", enctypes)]
    cp_conf.write()
    _logger.info("Wrote: %s", cp_path)
    return None


def ensure_krb5_ad_algos(
    sources: list[pathlib.Path] | None = None,
) -> None:
    """Ensure that needed algorithms for AD are present in krb5 config.

    NB: This function does not try to cover all possible krb5 configurations
    that might set permitted_enctypes. Rather, it exists to "mangle" the
    settings that are passed to a container on EL10 systems with FIPS enabled
    in order to ensure we can continue supporting AD. It is designed to give
    up or throw errors in the case of unexpected configurations.
    """
    if not sources:
        sources = [default_krb5_conf()] + conf_dir_files()
    krb_config = load(sources, ignore_missing=True)
    stop_cond = _check_files(krb_config)
    if not stop_cond:
        stop_cond = _check_content(krb_config)
    if not stop_cond:
        stop_cond = _update_algos(krb_config)
    if stop_cond and isinstance(stop_cond, _Ignore):
        _logger.debug("%s, skipping krb5 config update", stop_cond.reason)
    elif stop_cond:
        _logger.warning("%s, skipping krb5 config update", stop_cond.reason)
