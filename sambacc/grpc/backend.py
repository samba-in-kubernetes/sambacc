#
# sambacc: a samba container configuration tool (and more)
# Copyright (C) 2025  John Mulligan
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

from typing import Any, Callable, IO, Iterator, Optional, Protocol, Union

from functools import partial

import contextlib
import dataclasses
import enum
import io
import json
import logging
import os
import subprocess

from sambacc.typelets import Self
import sambacc.config
import sambacc.samba_cmds


_logger = logging.getLogger(__name__)
CTDB_CONF_PATH = "/etc/ctdb/ctdb.conf"


class ConfigReader(Protocol):
    def read_config(self) -> sambacc.config.GlobalConfig: ...
    def current_identity(self) -> str: ...


@dataclasses.dataclass
class Versions:
    samba_version: str = ""
    sambacc_version: str = ""
    container_version: str = ""


@dataclasses.dataclass
class SessionCrypto:
    cipher: str
    degree: str

    @classmethod
    def load(cls, json_object: dict[str, Any]) -> Self:
        cipher = json_object.get("cipher", "")
        cipher = "" if cipher == "-" else cipher
        degree = json_object.get("degree", "")
        return cls(cipher=cipher, degree=degree)


@dataclasses.dataclass
class Session:
    session_id: str
    username: str
    groupname: str
    remote_machine: str
    hostname: str
    session_dialect: str
    uid: int
    gid: int
    encryption: Optional[SessionCrypto] = None
    signing: Optional[SessionCrypto] = None

    @classmethod
    def load(cls, json_object: dict[str, Any]) -> Self:
        _encryption = json_object.get("encryption")
        encryption = SessionCrypto.load(_encryption) if _encryption else None
        _signing = json_object.get("signing")
        signing = SessionCrypto.load(_signing) if _signing else None
        return cls(
            session_id=json_object.get("session_id", ""),
            username=json_object.get("username", ""),
            groupname=json_object.get("groupname", ""),
            remote_machine=json_object.get("remote_machine", ""),
            hostname=json_object.get("hostname", ""),
            session_dialect=json_object.get("session_dialect", ""),
            uid=int(json_object.get("uid", -1)),
            gid=int(json_object.get("gid", -1)),
            encryption=encryption,
            signing=signing,
        )


@dataclasses.dataclass
class TreeConnection:
    tcon_id: str
    session_id: str
    service_name: str

    @classmethod
    def load(cls, json_object: dict[str, Any]) -> Self:
        return cls(
            tcon_id=json_object.get("tcon_id", ""),
            session_id=json_object.get("session_id", ""),
            service_name=json_object.get("service", ""),
        )


@dataclasses.dataclass
class Status:
    timestamp: str
    version: str
    sessions: list[Session]
    tcons: list[TreeConnection]

    @classmethod
    def load(cls, json_object: dict[str, Any]) -> Self:
        return cls(
            timestamp=json_object.get("timestamp", ""),
            version=json_object.get("version", ""),
            sessions=[
                Session.load(v)
                for _, v in json_object.get("sessions", {}).items()
            ],
            tcons=[
                TreeConnection.load(v)
                for _, v in json_object.get("tcons", {}).items()
            ],
        )

    @classmethod
    def parse(cls, txt: Union[str, bytes]) -> Self:
        return cls.load(json.loads(txt))


class ConfigFor(str, enum.Enum):
    SAMBA = "samba"
    CTDB = "ctdb"
    SAMBACC = "sambacc"
    SAMBA_SHARES = "shares"
    SAMBACC_SHARES = "sambacc-shares"


class ServerType(str, enum.Enum):
    SMB = "smbd"
    WINBIND = "winbindd"
    CTDB = "ctdb"


def debug_level_command(server: ServerType) -> sambacc.samba_cmds.CommandArgs:
    if server is ServerType.CTDB:
        return sambacc.samba_cmds.ctdb
    return sambacc.samba_cmds.smbcontrol


def _parse_debuglevel(command_output: str) -> str:
    parts = command_output.split()
    _pfx, _id, *rest = parts
    if _pfx != "PID" or not _id:
        raise ValueError(f"unexpected string in output: {command_output!r}")
    if rest[0].startswith("all:"):
        return rest[0].split(":", 1)[-1]
    raise ValueError(f"unexpected string in output: {command_output!r}")


@dataclasses.dataclass
class ShareEntry:
    name: str


@dataclasses.dataclass
class DumpItem:
    content: str
    line_number: int
    hash_type: Optional[str] = None

    def is_digest(self) -> bool:
        return self.hash_type is not None


class Dumper:
    def __init__(self, stream: IO, hash_alg: Optional[Callable]) -> None:
        self._stream = stream
        self._hash = None if hash_alg is None else hash_alg()
        self._enc = "utf-8"
        _logger.debug("Created dumper (with hash %r)", self._hash)

    def dump(self) -> Iterator[DumpItem]:
        for lnum, line in enumerate(self._stream):
            if self._hash:
                data = (
                    line if isinstance(line, bytes) else line.encode(self._enc)
                )
                self._hash.update(data)
            yield DumpItem(content=line, line_number=lnum)
        if self._hash:
            yield DumpItem(
                content=self._hash.hexdigest(),
                line_number=-1,
                hash_type=self._hash.name,
            )

    def digest(self) -> DumpItem:
        if not self._hash:
            _logger.error("Dumper.digest called without a hash set")
            raise ValueError("Dumper.digest requires a hash")
        _digests = [d for d in self.dump() if d.is_digest()]
        assert len(_digests) == 1
        return _digests[0]


@contextlib.contextmanager
def _cmdstream(
    cmd: Union[list, sambacc.samba_cmds.CommandArgs],
) -> Iterator[IO]:
    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
    )
    assert proc.stdout
    _logger.debug("command %r started", proc.args)
    try:
        yield proc.stdout
        ret = proc.wait()
    except Exception:
        proc.kill()
        proc.wait()
        raise
    _logger.debug("command %r exited with returncode=%r", proc.args, ret)
    if ret != 0:
        raise subprocess.CalledProcessError(ret, proc.args)


@contextlib.contextmanager
def config_samba() -> Iterator[IO]:
    _logger.debug("Streaming configuration from net conf list")
    cmd = sambacc.samba_cmds.net["conf", "list"]
    with _cmdstream(cmd) as stream:
        yield stream


@contextlib.contextmanager
def config_samba_shares() -> Iterator[IO]:
    _logger.debug("Streaming configuration from net conf listshares")
    cmd = sambacc.samba_cmds.net["conf", "listshares"]
    with _cmdstream(cmd) as stream:
        yield stream


@contextlib.contextmanager
def config_sambacc(config_reader: ConfigReader) -> Iterator[IO]:
    _logger.debug("Reading configuration for sambacc")
    gconfig = config_reader.read_config()
    buf = io.StringIO()
    json.dump(gconfig.data, buf, indent=2)
    buf.seek(0)
    yield buf


@contextlib.contextmanager
def config_sambacc_shares(config_reader: ConfigReader) -> Iterator[IO]:
    # Extract the shares from the current sambacc instance config
    _logger.debug("Reading configuration for sambacc (shares)")
    gconfig = config_reader.read_config()
    iconfig = gconfig.get(config_reader.current_identity())
    buf = io.StringIO()
    for share in iconfig.shares():
        buf.write(f"{share.name}\n")
    buf.seek(0)
    yield buf


@contextlib.contextmanager
def config_ctdb() -> Iterator[IO]:
    _logger.debug("Reading configuration file for ctdb")
    # there isn't a command from ctdb that shows the config so we can just
    # attempt to open the well known path of the config file
    with open(CTDB_CONF_PATH) as fh:
        yield fh


@contextlib.contextmanager
def config_stream(
    source: ConfigFor, config_reader: Optional[ConfigReader]
) -> Iterator[IO]:
    dump_fn = {
        ConfigFor.SAMBA: config_samba,
        ConfigFor.SAMBA_SHARES: config_samba_shares,
        ConfigFor.CTDB: config_ctdb,
    }
    if config_reader:
        dump_fn[ConfigFor.SAMBACC] = partial(config_sambacc, config_reader)
        dump_fn[ConfigFor.SAMBACC_SHARES] = partial(
            config_sambacc_shares, config_reader
        )
    try:
        fn = dump_fn[source]
    except KeyError:
        raise NotImplementedError(source)
    with fn() as stream:
        yield stream


class ControlBackend:
    def __init__(
        self,
        config: sambacc.config.InstanceConfig,
        *,
        config_reader: Optional[ConfigReader] = None,
    ) -> None:
        self._config = config
        self._reader = config_reader

    def _samba_version(self) -> str:
        smbd_ver = sambacc.samba_cmds.smbd["--version"]
        res = subprocess.run(list(smbd_ver), check=True, capture_output=True)
        return res.stdout.decode().strip()

    def _sambacc_version(self) -> str:
        try:
            import sambacc._version  # type: ignore

            return sambacc._version.version
        except ImportError:
            return "(unknown)"

    def _container_version(self) -> str:
        return os.environ.get("SAMBA_CONTAINER_VERSION", "(unknown)")

    def get_versions(self) -> Versions:
        versions = Versions()
        versions.samba_version = self._samba_version()
        versions.sambacc_version = self._sambacc_version()
        versions.container_version = self._container_version()
        return versions

    def is_clustered(self) -> bool:
        return self._config.with_ctdb

    def get_status(self) -> Status:
        smbstatus = sambacc.samba_cmds.smbstatus["--json"]
        proc = subprocess.Popen(
            list(smbstatus),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # TODO: the json output of smbstatus is potentially large
        # investigate streaming reads instead of fully buffered read
        # later
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"smbstatus error: {proc.returncode}: {stderr!r}"
            )
        return Status.parse(stdout)

    def close_share(self, share_name: str, denied_users: bool) -> None:
        _close = "close-denied-share" if denied_users else "close-share"
        cmd = sambacc.samba_cmds.smbcontrol["smbd", _close, share_name]
        subprocess.run(list(cmd), check=True)

    def kill_client(self, ip_address: str) -> None:
        cmd = sambacc.samba_cmds.smbcontrol[
            "smbd", "kill-client-ip", ip_address
        ]
        subprocess.run(list(cmd), check=True)

    def config_dump(
        self, src: ConfigFor, hash_alg: Optional[Callable]
    ) -> Iterator[DumpItem]:
        with config_stream(src, self._reader) as stream:
            yield from Dumper(stream, hash_alg).dump()

    def config_dump_digest(
        self, src: ConfigFor, hash_alg: Optional[Callable]
    ) -> DumpItem:
        with config_stream(src, self._reader) as stream:
            digest_item = Dumper(stream, hash_alg).digest()
        return digest_item

    def config_share_list(self, src: ConfigFor) -> Iterator[ShareEntry]:
        share_sources = {
            ConfigFor.SAMBA: ConfigFor.SAMBA_SHARES,
            ConfigFor.SAMBACC: ConfigFor.SAMBACC_SHARES,
        }
        try:
            alt_src = share_sources[src]
        except KeyError:
            raise NotImplementedError(src)
        with config_stream(alt_src, self._reader) as stream:
            for entry in Dumper(stream, None).dump():
                name = entry.content.strip()
                name_str = name if isinstance(name, str) else name.decode()
                # samba returns "global" as a share name even though it is the
                # name of the global configuration section and not really a
                # share. Elide it when listing configured shares.
                if name_str == "global":
                    continue
                yield ShareEntry(name=name_str)

    def set_debug_level(self, server: ServerType, debug_level: str) -> None:
        base_cmd = debug_level_command(server)
        if base_cmd is sambacc.samba_cmds.smbcontrol:
            cmd = base_cmd[server.value, "debug", debug_level]
        elif base_cmd is sambacc.samba_cmds.ctdb:
            cmd = base_cmd["setdebug", debug_level]
        else:
            raise ValueError(f"unexpected command: {base_cmd!r}")
        subprocess.run(list(cmd), check=True)

    def get_debug_level(self, server: ServerType) -> str:
        _parser = None
        base_cmd = debug_level_command(server)
        if base_cmd is sambacc.samba_cmds.smbcontrol:
            cmd = base_cmd[server.value, "debuglevel"]
            _parser = _parse_debuglevel
        elif base_cmd is sambacc.samba_cmds.ctdb:
            cmd = base_cmd["getdebug"]
        else:
            raise ValueError(f"unexpected command: {base_cmd!r}")
        res = subprocess.run(list(cmd), check=True, capture_output=True)
        output = res.stdout.decode().strip()
        return output if not _parser else _parser(output)
