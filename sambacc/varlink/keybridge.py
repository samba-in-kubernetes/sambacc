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


import base64
import dataclasses
import enum
import logging
import socket
import struct
import typing

import varlink  # type: ignore[import]

from sambacc.typelets import Self
from .endpoint import VarlinkEndpoint


_logger = logging.getLogger(__name__)


class KeyBridgeError(varlink.VarlinkError):
    _name: str = ""
    _expect: typing.Iterable = []

    def __init__(self, **kwargs: typing.Any) -> None:
        self._kwargs = kwargs
        if self._expect:
            for field in self._expect:
                if field not in self._kwargs:
                    raise ValueError(f"expected {field} in keyword arguments")
        super().__init__(
            {
                "error": self.full_name(),
                "parameters": self._kwargs,
            }
        )

    def error_name(self) -> str:
        assert self._name
        return self._name

    def full_name(self) -> str:
        return f"org.samba.containers.keybridge.{self.error_name()}"


class ScopeNotFoundError(KeyBridgeError):
    "ScopeName may be returned if a request refers to an unknown scope."
    _name = "ScopeNotFound"
    _expect = {"scope"}


class EntryNotFoundError(KeyBridgeError):
    "EntryNotFound may returned if a request refers to an unknown entry."
    _name = "EntryNotFound"
    _expect = {"name", "scope"}


class InvalidKindError(KeyBridgeError):
    """
    InvalidKind may be returned if a request refers to an unknown entry kind
    or a kind is not supported by the scope.
    """

    _name = "InvalidKind"


class ReadOnlyScope(KeyBridgeError):
    """
    ReadOnlyScope may be returned if a Set or Delete request is sent to a read
    only scope.
    """

    _name = "ReadOnlyScope"
    _expect = {"name"}


class OperationNotSupported(KeyBridgeError):
    """
    OperationNotSupported may be returned if an entry method is not supported
    by the given scope.
    """

    _name = "OperationNotSupported"
    _expect = {"op", "name", "scope"}


class OperationFailed(KeyBridgeError):
    """
    OperationFailed may be returned if an entry method is not currently
    functioning for the given scope. This could indicate the need to retry the
    operation later. It may provide a scope specific status and message for the
    reason the operation is not ready.

    The status value, if provided, should be a short string suitable for
    logging or parsing and creating conditional logic, but is scope-specific.
    The reason value, if provided, is a human-readable description of the
    problem.
    """

    _name = "OperationFailed"
    _expect = {"op", "name", "scope"}
    _optional = {"status", "reason"}


class OpKind(str, enum.Enum):
    GET = "Get"
    SET = "Set"
    DELETE = "Delete"


class EntryKind(str, enum.Enum):
    B64 = "B64"
    VALUE = "VALUE"


# KindStr can be used where a function can accept a str or EntryKind with the
# expectation it will be converted into an EntryKind.
KindStr = typing.Union[EntryKind, str]


@dataclasses.dataclass
class ScopeInfo:
    name: str
    default: bool
    kind: str
    description: str


@dataclasses.dataclass
class Entry:
    name: str
    scope: str
    kind: EntryKind
    data: typing.Optional[str] = None

    @classmethod
    def from_dict(cls, values: dict) -> Self:
        try:
            _kind = EntryKind(values["kind"])
        except ValueError:
            raise InvalidKindError()
        return cls(
            name=values["name"],
            scope=values["scope"],
            kind=_kind,
            data=values.get("data"),
        )


@dataclasses.dataclass
class ScopesResult:
    scopes: list[ScopeInfo]


@dataclasses.dataclass
class HasScopeResult:
    scope: typing.Optional[ScopeInfo] = None


@dataclasses.dataclass
class GetResult:
    entry: Entry


class KeyBridgeScope(typing.Protocol):
    """Protocol describing the core methods of a KeyBridge scope."""

    def name(self) -> str: ...
    def about(self) -> ScopeInfo: ...
    def get(self, key: str, kind: EntryKind) -> str: ...


class WritableKeyBridgeScope(KeyBridgeScope, typing.Protocol):
    """Protocol describing the methods of a writable scope."""

    def set(self, key: str, kind: EntryKind, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class PeerCheckingBridgeScope(KeyBridgeScope, typing.Protocol):
    """Protocol describing the methods of a scope that checks the validity of a
    peer for a given method (operation) type.
    Peer info is based on the process PID, UID, GID attached to the unix
    socket.
    """

    def verify_peer(
        self, op: OpKind, pid: int, uid: int, gid: int
    ) -> bool: ...


class _Request(typing.Protocol):
    """Protocol wrapping varlink (socket server) request objects."""

    def getsockopt(self, level: int, optname: int, buflen: int) -> bytes: ...


class KeyBridge:
    """The core KeyBridge implementation. The server fetches named keys
    from some sort of backend, called a scope. A scope may optionally
    support setting values or deleting keys. A scope may optionally
    support checking the validity of the peer process.
    The server has methods to report on the configured scopes.

    The core idea is to provide a flexible front-end for one or more secret
    services and a very simple protocol for samba to use to get secrets based
    on key names - avoiding having to put a bunch of different complex secrets
    systems implementations into smbd.
    """

    def __init__(self, scopes: list[KeyBridgeScope]) -> None:
        self._scopes = {scope.name(): scope for scope in scopes}

    def _verify(
        self,
        scope: KeyBridgeScope,
        op: OpKind,
        request: _Request,
        *,
        name: str = "",
        scope_name: str = "",
    ) -> None:
        _verify_peer = getattr(scope, "verify_peer", None)
        if not _verify_peer:
            _logger.debug("no verify_peer function for %s", scope.name())
            return
        creds = request.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
        )
        pid, uid, gid = struct.unpack("3i", creds)

        if _verify_peer(op, pid, uid, gid):
            _logger.debug(
                "peer process [%d, %d, %d] verified by %s",
                pid,
                uid,
                gid,
                scope.name(),
            )
            return
        _logger.warning(
            "peer process [%d, %d, %d] rejected by %s",
            pid,
            uid,
            gid,
            scope.name(),
        )
        raise OperationNotSupported(
            op=op.value,
            name=name,
            scope=scope_name,
        )

    def Scopes(self) -> ScopesResult:
        """Varlink method. List configure scopes."""
        _logger.debug("Called: Scopes")
        return ScopesResult(
            scopes=[scope.about() for scope in self._scopes.values()],
        )

    def HasScope(self, name: str) -> HasScopeResult:
        """Varlink method. Report if a named scope is configured."""
        _logger.debug("Called: HasScope")
        result = HasScopeResult()
        if scope := self._scopes.get(name):
            result.scope = scope.about()
        return result

    def Get(
        self, name: str, scope: str, kind: KindStr, _request: _Request
    ) -> GetResult:
        """Varlink method. Get a value from a scope. The kind controls the
        representation or encoding of the returned string. A scope is free to
        convert a value to a given kind or reject the request due to the kind
        not matching the data's encoding.
        """
        _logger.debug("Called: Get")
        try:
            _scope = self._scopes[scope]
        except KeyError:
            raise ScopeNotFoundError(scope=scope)
        self._verify(_scope, OpKind.GET, _request, name=name, scope_name=scope)
        try:
            _kind = EntryKind(kind)
        except ValueError:
            raise InvalidKindError()
        try:
            value = _scope.get(name, _kind)
        except KeyError:
            raise EntryNotFoundError(name=name, scope=scope)
        return GetResult(
            entry=Entry(
                name=name,
                scope=scope,
                kind=_kind,
                data=value,
            )
        )

    def Set(self, entry: dict, _request: _Request) -> None:
        """Varlink method. Create or update a key-value entry in a scope.
        Optional for a given scope.
        """
        _logger.debug("Called: Set")
        _entry = Entry.from_dict(entry)
        try:
            _scope = self._scopes[_entry.scope]
        except KeyError:
            raise ScopeNotFoundError(scope=_entry.scope)
        self._verify(
            _scope,
            OpKind.SET,
            _request,
            name=_entry.name,
            scope_name=_entry.scope,
        )
        _set = getattr(_scope, "set", None)
        if not _set:
            raise OperationNotSupported(
                op=OpKind.SET.value,
                name=_entry.name,
                scope=_entry.scope,
            )
        _set(_entry.name, _entry.kind, _entry.data)

    def Delete(self, name: str, scope: str, _request: _Request) -> None:
        """Varlink method. Delete an item from a scope. Optional for a given
        scope.
        """
        _logger.debug("Called: Delete")
        try:
            _scope = self._scopes[scope]
        except KeyError:
            raise ScopeNotFoundError(scope=scope)
        self._verify(_scope, OpKind.SET, _request, name=name, scope_name=scope)
        _delete = getattr(_scope, "delete", None)
        if not _delete:
            raise OperationNotSupported(
                op=OpKind.DELETE.value,
                name=name,
                scope=scope,
            )
        _delete(name)


def endpoint(scopes: list[KeyBridgeScope]) -> VarlinkEndpoint:
    """Return a new endpoint for the keybridge server that will be
    constructed using the supplied scope objects.
    """
    return VarlinkEndpoint(
        interface_filename="org.samba.containers.keybridge.varlink",
        interface_name="org.samba.containers.keybridge",
        interface_cls=KeyBridge,
        interface_kwargs={"scopes": scopes},
    )


class StaticValueScope:
    """Keybridge scope that contains simple static values.
    FOR TESTING ONLY.
    """

    def name(self) -> str:
        return "static_value_scope"

    def about(self) -> ScopeInfo:
        return ScopeInfo(
            self.name(),
            default=False,
            kind="test",
            description="static value test scope",
        )

    def get(self, key: str, kind: EntryKind) -> str:
        value = {
            "foo": b"foo-opolis",
            "bar": b"bar harbor",
            "baz": b"bazlee manor",
        }[key]
        if kind is EntryKind.B64:
            return base64.b64encode(value).decode()
        elif kind in EntryKind.VALUE:
            return value.decode()
        raise InvalidKindError()


class MemScope:
    """Keybridge scope that wrapping a simple dict-based in memory store.
    FOR TESTING ONLY.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, EntryKind]] = {}
        _logger.debug("Created MEM Scope: defaults=%r", self._entries)

    def name(self) -> str:
        return "mem"

    def about(self) -> ScopeInfo:
        return ScopeInfo(
            self.name(),
            default=False,
            kind="test",
            description="r/w in memory test scope",
        )

    def get(self, key: str, kind: EntryKind) -> str:
        value, value_kind = self._entries[key]
        if value_kind is not kind:
            raise InvalidKindError()
        return value

    def set(self, key: str, kind: EntryKind, value: str) -> None:
        self._entries[key] = (value, kind)

    def delete(self, key: str) -> None:
        self._entries.pop(key, None)


AllowedPeer = typing.Union[range, typing.Collection[int]]
AllowedPeerOpt = typing.Union[AllowedPeer, int, None]


def _allowed_peer(value: AllowedPeerOpt) -> AllowedPeer:
    if value is None:
        return set()
    if isinstance(value, int):
        return {value}
    return value


class VerifyPeerScopeWrapper:
    """Instead of coding every wrapper with peer verification logic,
    wrap a basic scope with the VerifyPeerScopeWrapper and let it
    handle peer verification.

    Checks are performed using one of an int, a range or a collection (set)
    of ints. The peer's PID, UID, GID is checked for belonging to the
    range/collection of allowed values.
    """

    def __init__(
        self,
        other: KeyBridgeScope,
        *,
        check_pid: AllowedPeerOpt = None,
        check_uid: AllowedPeerOpt = None,
        check_gid: AllowedPeerOpt = None,
    ) -> None:
        _logger.debug(
            (
                "Creating verify peer scope wrapper with"
                " check_pid=%r, check_uid=%r, check_gid=%r"
            ),
            check_pid,
            check_uid,
            check_gid,
        )
        self.other = other
        self._allowed_pids = _allowed_peer(check_pid)
        self._allowed_uids = _allowed_peer(check_uid)
        self._allowed_gids = _allowed_peer(check_gid)

    def verify_peer(self, op: OpKind, pid: int, uid: int, gid: int) -> bool:
        if self._allowed_pids and pid not in self._allowed_pids:
            return False
        if self._allowed_uids and uid not in self._allowed_uids:
            return False
        if self._allowed_gids and gid not in self._allowed_gids:
            return False
        return True

    def name(self) -> str:
        return self.other.name()

    def about(self) -> ScopeInfo:
        return self.other.about()

    def get(self, key: str, kind: EntryKind) -> str:
        return self.other.get(key, kind)

    def set(self, key: str, kind: EntryKind, value: str) -> None:
        _set = getattr(self.other, "set", None)
        if not _set:
            raise OperationNotSupported(
                op=OpKind.SET.value,
                name=key,
                scope=self.other.name(),
            )
        _set(key, kind, value)

    def delete(self, key: str) -> None:
        _delete = getattr(self.other, "delete", None)
        if not _delete:
            raise OperationNotSupported(
                op=OpKind.DELETE.value,
                name=key,
                scope=self.other.name(),
            )
        _delete(key)
