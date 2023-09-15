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

import typing
import urllib.request

from . import url_opener
from .typelets import ExcType, ExcValue, ExcTraceback

_RADOSModule = typing.Any

_CHUNK_SIZE = 4 * 1024


class RADOSUnsupported(Exception):
    pass


class _RADOSHandler(urllib.request.BaseHandler):
    _rados_api: typing.Optional[_RADOSModule] = None

    def rados_open(self, req: urllib.request.Request) -> typing.IO:
        if self._rados_api is None:
            raise RADOSUnsupported()
        sel = req.selector.lstrip("/")
        if req.host:
            pool = req.host
            ns, key = sel.split("/", 1)
        else:
            pool, ns, key = sel.split("/", 2)
        return _RADOSResponse(self._rados_api, pool, ns, key)


# it's quite annoying to have a read-only typing.IO we're forced to
# have so many stub methods. Go's much more granular io interfaces for
# readers/writers is much nicer for this.
class _RADOSResponse(typing.IO):
    def __init__(
        self, rados_api: _RADOSModule, pool: str, ns: str, key: str
    ) -> None:
        self._pool = pool
        self._ns = ns
        self._key = key

        self._open(rados_api)
        self._test()

    def _open(self, rados_api: _RADOSModule) -> None:
        # TODO: connection caching
        self._conn = rados_api.Rados()
        self._conn.conf_read_file()
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

    def __enter__(self) -> _RADOSResponse:
        return self

    def __exit__(
        self, exc_type: ExcType, exc_val: ExcValue, exc_tb: ExcTraceback
    ) -> None:
        self.close()

    def __iter__(self) -> _RADOSResponse:
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


def enable_rados_url_opener(cls: typing.Type[url_opener.URLOpener]) -> None:
    """Extend the URLOpener type to support pseudo-URLs for rados
    object storage. If rados libraries are not found the function
    does nothing.

    If rados libraries are found than URLOpener can be used like:
    >>> uo = url_opener.URLOpener()
    >>> res = uo.open("rados://my_pool/namepace/obj_key")
    >>> res.read()
    """
    try:
        import rados  # type: ignore[import]
    except ImportError:
        return

    _RADOSHandler._rados_api = rados
    cls._handlers.append(_RADOSHandler)
