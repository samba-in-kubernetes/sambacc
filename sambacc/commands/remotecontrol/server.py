#
# sambacc: a samba container configuration tool
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

import argparse
import logging
import signal
import sys
import typing

from ..cli import Context, Fail, commands

_logger = logging.getLogger(__name__)
_MTLS = "mtls"
_FORCE = "force"


def _serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--address",
        "-a",
        help="Specify an {address:port} value to bind to.",
    )
    # Force an explicit choice of (the only) rpc type in order to clearly
    # prepare the space for possible alternatives
    egroup = parser.add_mutually_exclusive_group(required=True)
    egroup.add_argument(
        "--grpc",
        dest="rpc_type",
        action="store_const",
        default="grpc",
        const="grpc",
        help="Use gRPC",
    )
    # security settings
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS",
    )
    parser.add_argument(
        "--allow-modify",
        choices=(_MTLS, _FORCE),
        default=_MTLS,
        help="Control modification mode",
    )
    parser.add_argument(
        "--tls-key",
        help="Server TLS Key",
    )
    parser.add_argument(
        "--tls-cert",
        help="Server TLS Certificate",
    )
    parser.add_argument(
        "--tls-ca-cert",
        help="CA Certificate",
    )


class Restart(Exception):
    pass


@commands.command(name="serve", arg_func=_serve_args)
def serve(ctx: Context) -> None:
    """Start an RPC server."""

    def _handler(*args: typing.Any) -> None:
        raise Restart()

    signal.signal(signal.SIGHUP, _handler)
    while True:
        try:
            _serve(ctx)
            return
        except KeyboardInterrupt:
            _logger.info("Exiting")
            sys.exit(0)
        except Restart:
            _logger.info("Re-starting server")
            continue


def _serve(ctx: Context) -> None:
    import sambacc.grpc.backend
    import sambacc.grpc.server

    config = sambacc.grpc.server.ServerConfig()
    config.insecure = bool(ctx.cli.insecure)
    if ctx.cli.address:
        config.address = ctx.cli.address
    if not (ctx.cli.insecure or ctx.cli.tls_key):
        raise Fail("Specify --tls-key=... or --insecure")
    if not (ctx.cli.insecure or ctx.cli.tls_cert):
        raise Fail("Specify --tls-cert=... or --insecure")
    if ctx.cli.tls_key:
        config.server_key = _read(ctx, ctx.cli.tls_key)
    if ctx.cli.tls_cert:
        config.server_cert = _read(ctx, ctx.cli.tls_cert)
    if ctx.cli.tls_ca_cert:
        config.ca_cert = _read(ctx, ctx.cli.tls_ca_cert)
    config.read_only = not (
        ctx.cli.allow_modify == _FORCE
        or (not config.insecure and config.ca_cert)
    )

    backend = sambacc.grpc.backend.ControlBackend(ctx.instance_config)
    sambacc.grpc.server.serve(config, backend)


def _read(ctx: Context, path_or_url: str) -> bytes:
    with ctx.opener.open(path_or_url) as fh:
        content = fh.read()
    return content if isinstance(content, bytes) else content.encode()
