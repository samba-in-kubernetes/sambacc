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
import binascii
import contextlib
import dataclasses
import errno
import logging
import threading
import time
import typing

from kmip.core import enums as kmip_enums  # type: ignore[import]
from kmip.pie.client import ProxyKmipClient  # type: ignore[import]
from kmip.pie.exceptions import KmipOperationFailure  # type: ignore[import]

from sambacc.varlink.keybridge import (
    EntryKind,
    EntryNotFoundError,
    OpKind,
    OperationFailed,
    ScopeInfo,
)


_logger = logging.getLogger(__name__)

# use monotonic if possible, otherwise fall back to traditional time.time.
try:
    _tf = time.monotonic
except AttributeError:
    _tf = time.time


@dataclasses.dataclass
class TLSPaths:
    cert: str
    key: str
    ca_cert: str


@dataclasses.dataclass
class _Value:
    "Cached value."
    value: bytes
    created: int


class KMIPScope:
    """Keybridge scope that proxies requests to a KMIP server."""

    _cache_age = 30  # seconds

    def __init__(
        self,
        kmip_name: str,
        *,
        hosts: typing.Collection[tuple[str, int]],
        tls_paths: TLSPaths,
    ) -> None:
        self.kmip_name = kmip_name
        self.hosts = hosts
        self.tls_paths = tls_paths
        self._kmip_version = kmip_enums.KMIPVersion.KMIP_1_2
        self._cache_lock = threading.Lock()
        self._kmip_cache: dict[str, _Value] = {}
        _logger.debug(
            "Created KMIP Scope with name=%r, hosts=%r, tls=%r",
            self.kmip_name,
            self.hosts,
            self.tls_paths,
        )

    def name(self) -> str:
        return f"kmip.{self.kmip_name}"

    def about(self) -> ScopeInfo:
        return ScopeInfo(
            self.name(),
            default=False,
            kind="KMIP",
            description="KMIP Server Proxy",
        )

    @contextlib.contextmanager
    def _client(self) -> typing.Iterator[ProxyKmipClient]:
        for hostname, port in self.hosts:
            try:
                client = ProxyKmipClient(
                    hostname=hostname,
                    port=port,
                    cert=self.tls_paths.cert,
                    key=self.tls_paths.key,
                    ca=self.tls_paths.ca_cert,
                    kmip_version=self._kmip_version,
                )
                client.open()
            except OSError as err:
                _logger.warning("failed to connect to %r: %s", hostname, err)
                _logger.debug("KMIP connect failure details", exc_info=True)
                continue
            try:
                yield client
            finally:
                client.close()
            return
        _logger.warning("exhausted list of KMIP hosts to try")
        raise OSError(errno.EHOSTUNREACH, "failed to connect to any host")

    @contextlib.contextmanager
    def _cache(
        self, prune: bool = False
    ) -> typing.Iterator[dict[str, _Value]]:
        with self._cache_lock:
            if prune:
                self._prune()
            yield self._kmip_cache

    def _timestamp(self) -> int:
        return int(_tf())

    def _prune(self) -> None:
        _now = self._timestamp()
        count = len(self._kmip_cache)
        self._kmip_cache = {
            k: v
            for k, v in self._kmip_cache.items()
            if _now < v.created + self._cache_age
        }
        _logger.debug(
            "pruned %s items from cache, now size %s",
            count - len(self._kmip_cache),
            len(self._kmip_cache),
        )

    @contextlib.contextmanager
    def _handle_kmip_error(
        self, op: OpKind, key: str
    ) -> typing.Iterator[None]:
        """Catch exceptions from KMIP libs and turn them into something
        more reasonable for a keybridge client.
        """
        try:
            yield
        except OSError as err:
            _logger.warning("KMIP connection failed: %s", err)
            raise OperationFailed(
                op=op.value,
                name=key,
                scope=self.name(),
                status="KMIP_CONNECTION_FAILED",
                reason=str(err),
            )
        except KmipOperationFailure as kmip_err:
            _logger.debug("KMIP operation failure: %s", kmip_err)
            reason = getattr(kmip_err, "reason", None)
            if (
                reason is kmip_enums.ResultReason.ITEM_NOT_FOUND
                or reason is kmip_enums.ResultReason.PERMISSION_DENIED
            ):
                raise EntryNotFoundError(
                    name=key,
                    scope=self.name(),
                ) from kmip_err
            _logger.warning("unexpected KMIP operation failure: %s", kmip_err)
            raise OperationFailed(
                op=op.value,
                name=key,
                scope=self.name(),
                status="KMIP_OPERATION_FAILED",
                reason=str(kmip_err),
            ) from kmip_err

    def get(self, key: str, kind: EntryKind) -> str:
        """Get a value associated with the given key from the KMIP server or
        cache. If entry kind is B64 the (typically) binary data will be base64
        encoded. keybridge clients are expected to decode B64 on their side. If
        VALUE is given, return a hexlified version of the data similar to what
        the KMIP library does - for easier debugging.
        """
        with self._cache(prune=True) as cache:
            if key in cache:
                _logger.debug("KMIP cache hit: %r", key)
                return _format(cache[key].value, kind)
        with self._handle_kmip_error(OpKind.GET, key):
            with self._client() as client:
                result = client.get(key)
        _logger.debug("KMIP result for: %r", key)
        with self._cache() as cache:
            cache[key] = _Value(result.value, created=self._timestamp())
        return _format(result.value, kind)


def _format(raw_data: bytes, kind: EntryKind) -> str:
    if kind is EntryKind.VALUE:
        return binascii.hexlify(raw_data).decode()
    return base64.b64encode(raw_data).decode()
