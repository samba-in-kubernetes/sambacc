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

import errno
import http
import typing
import urllib.error
import urllib.request

from .opener import SchemeNotSupported


class _UnknownHandler(urllib.request.BaseHandler):
    def unknown_open(self, req: urllib.request.Request) -> None:
        raise SchemeNotSupported(req.full_url)


class URLOpener:
    """An Opener type used for fetching remote resources named in
    a pseudo-URL (URI-like) style.
    By default works like urllib.urlopen but only for HTTP(S).

    Example:
    >>> uo = URLOpener()
    >>> res = uo.open("http://abc.example.org/foo/x.json")
    >>> res.read()
    """

    # this list is similar to the defaults found in build_opener
    # but only for http/https handlers. No FTP, etc.
    _handlers = [
        urllib.request.ProxyHandler,
        urllib.request.HTTPHandler,
        urllib.request.HTTPDefaultErrorHandler,
        urllib.request.HTTPRedirectHandler,
        urllib.request.HTTPErrorProcessor,
        urllib.request.HTTPSHandler,
        _UnknownHandler,
    ]

    def __init__(self) -> None:
        self._opener = urllib.request.OpenerDirector()
        for handler in self._handlers:
            self._opener.add_handler(handler())

    def open(self, url: str) -> typing.IO:
        try:
            return self._opener.open(url)
        except ValueError as err:
            # too bad urllib doesn't use a specific subclass of ValueError here
            if "unknown url type" in str(err):
                raise SchemeNotSupported(url) from err
            raise
        except urllib.error.HTTPError as err:
            _map_errno(err)
            raise


_EMAP = {
    http.HTTPStatus.NOT_FOUND.value: errno.ENOENT,
    http.HTTPStatus.UNAUTHORIZED.value: errno.EPERM,
}


def _map_errno(err: urllib.error.HTTPError) -> None:
    """While HTTPError is an OSError, it often doesn't have an errno set.
    Since our callers care about the errno, do a best effort mapping of
    some HTTP statuses to errnos.
    """
    if getattr(err, "errno", None) is not None:
        return
    status = int(getattr(err, "status", -1))
    setattr(err, "errno", _EMAP.get(status, None))
