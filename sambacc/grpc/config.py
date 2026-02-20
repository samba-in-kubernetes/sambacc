#
# sambacc: a samba container configuration tool (and more)
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

from typing import Optional, Protocol

import dataclasses
import enum

from ..typelets import Self


class ClientVerification(str, enum.Enum):
    INSECURE = "insecure"
    TLS = "tls"
    TOKEN = "magic-token"


class Level(enum.Enum):
    READ = 1
    MODIFY = 2
    DEBUG_READ = 3


class ClientCheckerConfig(Protocol):
    def can_verify(self, cv: ClientVerification) -> bool: ...


@dataclasses.dataclass
class ConnectionConfig:
    address: str = "localhost:54445"
    verification: ClientVerification = ClientVerification.INSECURE
    server_key: Optional[bytes] = None
    server_cert: Optional[bytes] = None
    ca_cert: Optional[bytes] = None
    checker_conf: Optional[ClientCheckerConfig] = None

    @classmethod
    def from_dict(cls, config: dict) -> Self:
        return cls(
            **{
                field.name: config[field.name]
                for field in dataclasses.fields(cls)
                if field.name in config
            }
        )

    def describe(self) -> str:
        _kind = "tcp socket"
        if self.address.startswith("unix:"):
            _kind = "unix socket"
        return f"{_kind}/{self.verification.value}"

    @property
    def uses_tls(self) -> bool:
        return self.verification is ClientVerification.TLS

    # compat properties
    @property
    def insecure(self) -> bool:
        return self.verification in {
            ClientVerification.INSECURE,
            ClientVerification.TOKEN,
        }

    @insecure.setter
    def insecure(self, value: bool) -> None:
        self.verification = (
            ClientVerification.INSECURE if value else ClientVerification.TLS
        )


@dataclasses.dataclass
class ServerConfig:
    max_workers: int
    read_only: bool
    connections: list[ConnectionConfig]

    @classmethod
    def default(cls) -> Self:
        return cls(
            max_workers=8,
            read_only=False,
            connections=[ConnectionConfig()],
        )

    def first_connection(self) -> ConnectionConfig:
        return self.connections[0]


@dataclasses.dataclass
class MagicTokenConfig:
    env_var: str
    header_key: str = "magic-token"

    def can_verify(self, cv: ClientVerification) -> bool:
        if not self.env_var:
            raise ValueError("env_var invalid")
        if not self.header_key:
            raise ValueError("header_key invalid")
        return cv is ClientVerification.TOKEN
