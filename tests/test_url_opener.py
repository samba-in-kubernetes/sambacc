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
import http.server
import os
import sys
import threading
import urllib.request

import pytest

import sambacc.url_opener


class _Server:
    def __init__(self, port=8111):
        port = int(os.environ.get("SAMBACC_TEST_HTTP_PORT", port))
        self._port = port
        self._server = http.server.HTTPServer(("127.0.0.1", port), _Handler)

    @property
    def port(self):
        return self._port

    def start(self):
        self._t = threading.Thread(target=self._server.serve_forever)
        self._t.start()

    def stop(self):
        sys.stdout.flush()
        self._server.shutdown()
        self._t.join()


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        word = self.path.split("/")[-1]
        method = f"get_{word}"
        return getattr(self, method)()

    def get_a(self):
        return self._ok("Wilbur was Right")

    def get_b(self):
        return self._ok("This is a test")

    def get_err404(self):
        self._err(http.HTTPStatus.NOT_FOUND, "Not Found")

    def get_err401(self):
        self._err(http.HTTPStatus.UNAUTHORIZED, "Unauthorized")

    def get_err403(self):
        self._err(http.HTTPStatus.FORBIDDEN, "Forbidden")

    def _ok(self, value):
        self.send_response(http.HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(value)))
        self.end_headers()
        self.wfile.write(value.encode("utf8"))

    def _err(self, err_value, err_msg):
        self.send_response(err_value)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(err_msg)))
        self.end_headers()
        self.wfile.write(err_msg.encode("utf8"))


@pytest.fixture(scope="module")
def http_server():
    srv = _Server()
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


def test_success_1(http_server):
    url = f"http://localhost:{http_server.port}/a"
    opener = sambacc.url_opener.URLOpener()
    res = opener.open(url)
    assert res.read() == b"Wilbur was Right"


def test_success_2(http_server):
    url = f"http://localhost:{http_server.port}/b"
    opener = sambacc.url_opener.URLOpener()
    res = opener.open(url)
    assert res.read() == b"This is a test"


def test_error_404(http_server):
    url = f"http://localhost:{http_server.port}/err404"
    opener = sambacc.url_opener.URLOpener()
    with pytest.raises(OSError) as err:
        opener.open(url)
    assert err.value.status == 404
    assert err.value.errno == errno.ENOENT


def test_error_401(http_server):
    url = f"http://localhost:{http_server.port}/err401"
    opener = sambacc.url_opener.URLOpener()
    with pytest.raises(OSError) as err:
        opener.open(url)
    assert err.value.status == 401
    assert err.value.errno == errno.EPERM


def test_error_403(http_server):
    url = f"http://localhost:{http_server.port}/err403"
    opener = sambacc.url_opener.URLOpener()
    with pytest.raises(OSError) as err:
        opener.open(url)
    assert err.value.status == 403
    # No errno mapped for this one


def test_map_errno(http_server):
    url = f"http://localhost:{http_server.port}/err401"
    opener = sambacc.url_opener.URLOpener()
    with pytest.raises(OSError) as err:
        opener.open(url)
    # do not replace an existing errno
    err.value.errno = errno.EIO
    sambacc.url_opener._map_errno(err.value)
    assert err.value.errno == errno.EIO


def test_unknown_url():
    opener = sambacc.url_opener.URLOpener()
    with pytest.raises(sambacc.url_opener.SchemeNotSupported):
        opener.open("bloop://foo/bar/baz")


def test_unknown_url_type():
    opener = sambacc.url_opener.URLOpener()
    with pytest.raises(sambacc.url_opener.SchemeNotSupported):
        opener.open("bonk-bonk-bonk")


def test_value_error_during_handling():
    class H(urllib.request.BaseHandler):
        def bonk_open(self, req):
            raise ValueError("fiddlesticks")

    class UO(sambacc.url_opener.URLOpener):
        _handlers = sambacc.url_opener.URLOpener._handlers + [H]

    opener = UO()
    with pytest.raises(ValueError) as err:
        opener.open("bonk:bonk")
    assert str(err.value) == "fiddlesticks"
