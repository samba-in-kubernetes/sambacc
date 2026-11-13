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

configparser is not used as it can not handle the nested groups and
include directives that
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
_DIRECTIVES = ("include", "includedir", "module")
# Names of files in a config directory that the MIT library will read.
_DIR_FILE_RE = re.compile(r"^[A-Za-z0-9_-]+$|\.conf$")
_INDENT = 4


class KrbConfError(ValueError):
    """Raised when krb5.conf content can not be parsed."""


type Value = str | Group
type KeyValue = tuple[str, Value]


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
        """Get a single value from the group even if there are many.
        Return default if no value found for given key.
        """
        return dict(self.items).get(key, default)

    def get_all(self, key: str) -> list[KeyValue]:
        """Return a list of all KeyValue pairs matching the provided key."""
        return [kv for kv in self.items if key == kv[0]]


type _NLine = tuple[int, str]


def _is_directive(line: str) -> bool:
    return line.split(None, 1)[0] in _DIRECTIVES


class KrbConfLoader(TextFileLoader):
    """A single krb5.conf style file."""

    def __init__(self, path: str):
        super().__init__(path)
        self.sections: dict[str, Group] = {}
        self.directives: dict[int, tuple[str, str]] = {}

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
            elif _is_directive(line):
                self._parse_directive(lnum, line)
                _logger.debug("ignoring directive: %s", line)
            elif line == "}":
                self._error(lnum, "unmatched '}'")
            elif not section:
                self._error(lnum, "content outside of a section")
            else:
                self._parse_kv(lines, self.sections[section], lnum, line)

    def _parse_kv(
        self,
        lines: Iterable[_NLine],
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
        self._parse_group(lines, lnum, inner_group)
        dest.add(key, inner_group)

    def _parse_group(
        self,
        lines: Iterable[_NLine],
        start: int,
        dest: Group,
    ) -> None:
        """Parse lines into `group` up to its closing "}"."""
        for lnum, line in lines:
            if line == "}":
                return
            if _is_directive(line):
                self._error(lnum, f"unexpected directive inside block: {line}")
            self._parse_kv(lines, dest, lnum, line)
        self._error(start, "unterminated '{' group")

    def _parse_directive(self, lnum: int, line: str) -> None:
        # directives are typically only going to be in the main krb5.conf
        # but we don't care to enforce that at this time
        values = line.split(None, 1)
        assert len(values) == 2
        self.directives[lnum] = typing.cast(tuple[str, str], tuple(values))

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

    def has_directive(self, directive: str, value: str) -> bool:
        return (directive, value) in {
            (dk, dv) for (dk, dv) in self.directives.values()
        }


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
            for lnum, directive in src_conf.directives.items():
                merged_conf.directives[lnum] = directive
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
    missing directory is treated as empty.
    """
    try:
        paths = sorted(pathlib.Path(path).iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return []
    return [p for p in paths if _DIR_FILE_RE.search(p.name) and p.is_file()]


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


def ensure_krb5_ad_algos(
    sources: list[pathlib.Path] | None = None,
) -> None:
    """Ensure that needed algorithms for AD are present in krb5 config."""
    if not sources:
        sources = [default_krb5_conf()] + conf_dir_files()
    krb_config = load(sources, ignore_missing=True)
    pth_kc = krb_config.find("krb5.conf")
    if not pth_kc:
        _logger.debug("no krb5.conf found, skipping krb5 config update")
        return
    kc = pth_kc[1]
    if not (
        kc.has_directive("includedir", KRB5_CONF_DIR)
        or kc.has_directive("includedir", f"{KRB5_CONF_DIR}/")
    ):
        _logger.debug(
            "no krb5.conf includedir found, skipping krb5 config update"
        )
        return
    merged = krb_config.merged()
    merged_libdefaults = merged.sections.get("libdefaults")
    if not merged_libdefaults:
        _logger.debug(
            "no libdefaults section found, skipping krb5 config update"
        )
        return
    enctypes = merged_libdefaults.get("permitted_enctypes")
    if not enctypes:
        _logger.debug(
            "no permitted_enctypes key found, skipping krb5 config update"
        )
        return
    if not (pcc := krb_config.find("crypto-policies")):
        _logger.debug(
            "no crypto-policies file found, skipping krb5 config update"
        )
        return
    # all these files in the wild are just simple assignments
    assert isinstance(enctypes, str)
    enclist = enctypes.split()
    missing = False
    for alg in ("aes256-cts-hmac-sha1-96", "aes128-cts-hmac-sha1-96"):
        if alg not in enclist:
            enctypes = f"{enctypes} {alg}"
            missing = True
    if not missing:
        _logger.debug(
            "ad support algorithms found, skipping krb5 config update"
        )
        return
    cp_path, cp_conf = pcc
    _logger.info("Updating kerberos config: %s", cp_path)
    libdefaults = cp_conf.sections["libdefaults"]
    # all these files in the wild should just have the one permitted_enctypes
    # line. we're adding in missing required enctypes so we can reset the
    # whole config file contents to permitted_enctypes
    assert len(libdefaults.items) == 1
    libdefaults.items = [("permitted_enctypes", enctypes)]
    cp_conf.write()
    _logger.info("Wrote: %s", cp_path)
