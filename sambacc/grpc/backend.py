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

from typing import Any, Union, Optional

import dataclasses
import json
import os
import subprocess

from sambacc.typelets import Self
import sambacc.config
import sambacc.samba_cmds


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


class ControlBackend:
    def __init__(self, config: sambacc.config.InstanceConfig) -> None:
        self._config = config

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
