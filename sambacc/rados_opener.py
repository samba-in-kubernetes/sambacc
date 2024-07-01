#
# sambacc: a samba container configuration tool
# Copyright (C) 2023  John Mulligan
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

import io
import json
import logging
import time
import typing
import urllib.request
import uuid

from . import url_opener
from .typelets import ExcType, ExcValue, ExcTraceback, Self

_RADOSModule = typing.Any
_RADOSObject = typing.Any

_CHUNK_SIZE = 4 * 1024

_logger = logging.getLogger(__name__)


class RADOSUnsupported(Exception):
    pass


class _RADOSInterface:
    api: _RADOSModule
    client_name: str
    full_name: bool

    def Rados(self) -> _RADOSObject:
        name = rados_id = ""
        if self.full_name:
            name = self.client_name
        else:
            rados_id = self.client_name
        _logger.debug("Creating RADOS connection")
        return self.api.Rados(
            name=name,
            rados_id=rados_id,
            conffile=self.api.Rados.DEFAULT_CONF_FILES,
        )


class _RADOSHandler(urllib.request.BaseHandler):
    _interface: typing.Optional[_RADOSInterface] = None

    def rados_open(self, req: urllib.request.Request) -> typing.IO:
        """Open a rados-style url. Called from urllib."""
        if self._interface is None:
            raise RADOSUnsupported()
        rinfo = parse_rados_uri(req)
        if rinfo.get("subtype") == "mon-config-key":
            return _get_mon_config_key(self._interface, rinfo["path"])
        return RADOSObjectRef(
            self._interface, rinfo["pool"], rinfo["ns"], rinfo["key"]
        )

    def get_object(
        self, uri: str, *, must_exist: bool = False
    ) -> RADOSObjectRef:
        """Return a rados object reference for the given rados uri. The uri
        must refer to a rados object only as the RADOSObjectRef can do various
        rados-y things, more than an IO requires.
        """
        if self._interface is None:
            raise RADOSUnsupported()
        rinfo = parse_rados_uri(urllib.request.Request(uri))
        if rinfo.get("type") != "rados":
            raise ValueError("only rados URI values supported")
        if rinfo.get("subtype") == "mon-config-key":
            raise ValueError("only rados object URI values supported")
        return RADOSObjectRef(
            self._interface,
            rinfo["pool"],
            rinfo["ns"],
            rinfo["key"],
            must_exist=must_exist,
        )


# it's quite annoying to have a read-only typing.IO we're forced to
# have so many stub methods. Go's much more granular io interfaces for
# readers/writers is much nicer for this.
class RADOSObjectRef(typing.IO):
    def __init__(
        self,
        interface: _RADOSInterface,
        pool: str,
        ns: str,
        key: str,
        *,
        must_exist: bool = True,
    ) -> None:
        self._pool = pool
        self._ns = ns
        self._key = key
        self._lock_description = "sambacc RADOS library"
        self._lock_duration = None

        self._open(interface)
        if must_exist:
            self._test()

    def _open(self, interface: _RADOSInterface) -> None:
        # TODO: connection caching
        self._api = interface.api
        self._conn = interface.Rados()
        self._conn.connect()
        self._connected = True
        self._ioctx = self._conn.open_ioctx(self._pool)
        self._ioctx.set_namespace(self._ns)
        self._closed = False
        self._offset = 0

    def _test(self) -> None:
        self._ioctx.stat(self._key)

    def read(self, size: typing.Optional[int] = None) -> bytes:
        if self._closed:
            raise ValueError("can not read from closed response")
        return self._read_all() if size is None else self._read(size)

    def _read_all(self) -> bytes:
        ba = bytearray()
        while True:
            chunk = self._read(_CHUNK_SIZE)
            ba += chunk
            if len(chunk) < _CHUNK_SIZE:
                break
        return bytes(ba)

    def _read(self, size: int) -> bytes:
        result = self._ioctx.read(self._key, size, self._offset)
        self._offset += len(result)
        return result

    def close(self) -> None:
        if not self._closed:
            self._ioctx.close()
            self._closed = True
        if self._connected:
            self._conn.shutdown()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def mode(self) -> str:
        return "rb"

    @property
    def name(self) -> str:
        return self._key

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: ExcType, exc_val: ExcValue, exc_tb: ExcTraceback
    ) -> None:
        self.close()

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> bytes:
        res = self.read(_CHUNK_SIZE)
        if not res:
            raise StopIteration()
        return res

    def seekable(self) -> bool:
        return False

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def tell(self) -> int:
        return self._offset

    def seek(self, offset: int, whence: int = 0) -> int:
        raise NotImplementedError()

    def fileno(self) -> int:
        raise NotImplementedError()

    def readline(self, limit: int = -1) -> bytes:
        raise NotImplementedError()

    def readlines(self, hint: int = -1) -> list[bytes]:
        raise NotImplementedError()

    def truncate(self, size: typing.Optional[int] = None) -> int:
        raise NotImplementedError()

    def write(self, s: typing.Any) -> int:
        raise NotImplementedError()

    def writelines(self, ls: typing.Iterable[typing.Any]) -> None:
        raise NotImplementedError()

    def write_full(self, data: bytes) -> None:
        """Write the object such that its contents are exactly `data`."""
        self._ioctx.write_full(self._key, data)

    def _lock_exclusive(self, name: str, cookie: str) -> None:
        self._ioctx.lock_exclusive(
            self._key,
            name,
            cookie,
            desc=self._lock_description,
            duration=self._lock_duration,
        )

    def _acquire_lock_exclusive(
        self, name: str, cookie: str, *, delay: int = 1
    ) -> None:
        while True:
            try:
                self._lock_exclusive(name, cookie)
                return
            except self._api.ObjectBusy:
                _logger.debug(
                    "lock failed: %r, %r, %r: object busy",
                    self._key,
                    name,
                    cookie,
                )
                time.sleep(delay)

    def _unlock(self, name: str, cookie: str) -> None:
        self._ioctx.unlock(self._key, name, cookie)


def _get_mon_config_key(interface: _RADOSInterface, key: str) -> io.BytesIO:
    mcmd = json.dumps(
        {
            "prefix": "config-key get",
            "key": str(key),
        }
    )
    with interface.Rados() as rc:
        ret, out, err = rc.mon_command(mcmd, b"")
        if ret == 0:
            # We need to return a file like object. Since we are handed just
            # bytes from this api, use BytesIO to adapt it to something valid.
            return io.BytesIO(out)
        # ensure ceph didn't send us a negative errno
        ret = ret if ret > 0 else -ret
        msg = f"failed to get mon config key: {key!r}: {err}"
        raise OSError(ret, msg)


class ClusterMetaRADOSHandle:
    "A Cluster Meta Object can load or dump persistent cluster descriptions."

    def __init__(
        self,
        rados_obj: RADOSObjectRef,
        uri: str,
        *,
        read: bool,
        write: bool,
        locked: bool,
    ):
        self._rados_obj = rados_obj
        self._uri = uri
        self._read = read
        self._write = write
        self._locked = locked
        if self._locked:
            self._lock_name = "cluster_meta"
            self._cookie = f"sambacc:{uuid.uuid4()}"

    def load(self) -> typing.Any:
        if not self._read:
            raise ValueError("not readable")
        buf = self._rados_obj.read()
        if not buf:
            return {}
        return json.loads(buf)

    def dump(self, data: typing.Any) -> None:
        if not self._read:
            raise ValueError("not writable")
        buf = json.dumps(data).encode("utf8")
        self._rados_obj.write_full(buf)

    def __enter__(self) -> Self:
        if self._locked:
            self._rados_obj._acquire_lock_exclusive(
                self._lock_name, self._cookie
            )
        return self

    def __exit__(
        self, exc_type: ExcType, exc_val: ExcValue, exc_tb: ExcTraceback
    ) -> None:
        if self._locked:
            self._rados_obj._unlock(self._lock_name, self._cookie)
        return


class ClusterMetaRADOSObject:
    def __init__(self, rados_handler: _RADOSHandler, uri: str) -> None:
        self._handler = rados_handler
        self._uri = uri

    def open(
        self, *, read: bool = True, write: bool = False, locked: bool = False
    ) -> ClusterMetaRADOSHandle:
        return ClusterMetaRADOSHandle(
            self._handler.get_object(self._uri),
            self._uri,
            read=read,
            write=write,
            locked=locked,
        )

    @classmethod
    def create_from_uri(cls, uri: str) -> Self:
        """Return a new ClusterMetaRADOSObject given a rados uri string.
        If rados module is unavailable RADOSUnsupported will be raised.
        """
        handler = _RADOSHandler()
        if not handler._interface:
            raise RADOSUnsupported()
        return cls(handler, uri)


def is_rados_uri(uri: str) -> bool:
    """Return true if the string can be used as a rados (pseudo) URI.
    This function does not require the rados libraries to be available.
    NB: It does not validate the structure of the URI.
    """
    return uri.startswith("rados:")


def parse_rados_uri(
    uri: typing.Union[str, urllib.request.Request]
) -> dict[str, str]:
    """Given a rados uri-like value return a dict containing a breakdown of the
    components of the uri.
    """
    req = uri if not isinstance(uri, str) else urllib.request.Request(uri)
    subtype = "mon-config-key"
    if req.selector.startswith(subtype + ":"):
        return {
            "type": req.type,
            "subtype": subtype,
            "path": req.selector.split(":", 1)[1],
        }
    sel = req.selector.lstrip("/")
    if req.host:
        pool = req.host
        ns, key = sel.split("/", 1)
    else:
        pool, ns, key = sel.split("/", 2)
    return {
        "type": req.type,
        "subtype": "object",
        "pool": pool,
        "ns": ns,
        "key": key,
    }


def enable_rados(
    cls: typing.Type[url_opener.URLOpener],
    *,
    client_name: str = "",
    full_name: bool = False,
) -> None:
    """Enable Ceph RADOS support in sambacc.
    As as side-effect it will extend the URLOpener type to support pseudo-URLs
    for rados object storage. It will also enable the
    ClusterMetaRADOSObject.create_from_uri constructor. If rados libraries are
    not found the function does nothing.

    If rados libraries are found than URLOpener can be used like:
    >>> uo = url_opener.URLOpener()
    >>> res = uo.open("rados://my_pool/namepace/obj_key")
    >>> res.read()
    """
    try:
        import rados  # type: ignore[import]
    except ImportError:
        _logger.debug("Failed to import ceph 'rados' module")
        return

    _logger.debug(
        "Enabling ceph rados support with"
        f" client_name={client_name!r}, full_name={full_name}"
    )
    rados_interface = _RADOSInterface()
    rados_interface.api = rados
    rados_interface.client_name = client_name
    rados_interface.full_name = full_name

    _RADOSHandler._interface = rados_interface
    cls._handlers.append(_RADOSHandler)
