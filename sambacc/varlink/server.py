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


import contextlib
import dataclasses
import importlib.resources
import logging
import threading
import typing

import varlink  # type: ignore[import]
import varlink.error  # type: ignore[import]
import varlink.server  # type: ignore[import]

from .endpoint import VarlinkEndpoint


_logger = logging.getLogger(__name__)

_VET = typing.Type[varlink.error.VarlinkEncoder]
_varlink_VarlinkEncoder: _VET = varlink.error.VarlinkEncoder


class VarlinkEncoder(_varlink_VarlinkEncoder):
    """Custom varlink encoder supporting dataclasses."""

    def default(self, obj: typing.Any) -> typing.Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            dct = dataclasses.asdict(obj)
            return dct
        return super().default(obj)


def patch_varlink_encoder() -> None:
    """Monkeypatch varlink encoder to enable dataclass support."""
    varlink.error.VarlinkEncoder = VarlinkEncoder
    varlink.server.VarlinkEncoder = VarlinkEncoder


class VarlinkServerOptions:
    """Options used to configure the sambacc varlink server."""

    address: str
    vendor: str = "sambacc"
    version: str = "1"
    product: str = ""

    def __init__(
        self,
        address: str,
        vendor: str = "",
        version: str = "",
        product: str = "",
    ) -> None:
        self.address = address
        if vendor:
            self.vendor = vendor
        if version:
            self.version = version
        if product:
            self.product = product


class VarlinkServer:
    """Varlink server core.
    Use add_endpoint to attach new endpoint objects to the server. The endpoint
    objects map to varlink interfaces.
    Use serve function to start serving.
    """

    def __init__(
        self,
        options: VarlinkServerOptions,
        endpoints: typing.Optional[list[VarlinkEndpoint]] = None,
    ) -> None:
        self.options = options
        self.endpoints: list[VarlinkEndpoint] = []
        for ep in endpoints or []:
            self.add_endpoint(ep)
        # internal attributes
        self._service: typing.Optional[varlink.Service] = None
        self._server: typing.Optional[varlink.Server] = None

    def add_endpoint(self, endpoint: VarlinkEndpoint) -> None:
        """Add a new endpoint object to the server object."""
        assert endpoint.interface_filename
        assert endpoint.interface_name
        assert endpoint.interface_cls
        self.endpoints.append(endpoint)

    def _make_service(self) -> varlink.Service:
        svc = varlink.Service(
            vendor=self.options.vendor,
            product=self.options.product,
            version=self.options.version,
        )
        for ep in self.endpoints:
            self._attach(svc, ep)
        return svc

    def _attach(self, svc: varlink.Service, endpoint: VarlinkEndpoint) -> None:
        """Associate a varlink library service with a sambacc varlink endpoint.
        This is the main glue function between the way sambacc does things
        and the varlink library style of working.
        This is also where we use importlib to get the interface vs. the
        library's file-path based mechanism.
        """
        if_data = importlib.resources.read_text(
            endpoint.location,
            endpoint.interface_filename,
        )
        interface = varlink.Interface(if_data)
        _logger.debug("Read interface data for %s", interface.name)
        handler = endpoint.interface_cls(**endpoint.interface_kwargs)
        svc.interfaces[interface.name] = interface
        svc.interfaces_handlers[interface.name] = handler
        _logger.debug("Attached handler for %s", interface.name)

    def _request_handler_cls(self, svc: varlink.Service) -> typing.Any:
        class Handler(varlink.RequestHandler):
            service = svc

        return Handler

    def _make_server(self) -> None:
        """Create the varlink library server object."""
        self._service = self._make_service()
        self._server = varlink.ThreadingServer(
            self.options.address, self._request_handler_cls(self._service)
        )
        _logger.debug("Created new varlink server")

    @contextlib.contextmanager
    def serve(self) -> typing.Iterator[None]:
        """Returns a context manager that Runs the varlink server in a thread,
        terminating the server when the context manager exits.
        """
        if not self._server:
            self._make_server()
        assert self._server
        self._serve_thread = threading.Thread(
            target=self._server.serve_forever
        )
        self._serve_thread.start()
        _logger.debug("started server thread")
        try:
            yield
        finally:
            _logger.debug("shutting down server...")
            self._server.shutdown()
            _logger.debug("waiting for thread...")
            self._serve_thread.join()
