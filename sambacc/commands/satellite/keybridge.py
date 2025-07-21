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
import pathlib
import signal
import sys
import typing

import sambacc.config

from ..cli import Context, Fail, commands


if typing.TYPE_CHECKING:
    import sambacc.varlink.keybridge

    Scope = sambacc.varlink.keybridge.KeyBridgeScope
else:
    Scope = typing.Any


_logger = logging.getLogger(__name__)


def _serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config-section",
        default="",
        help="Select a keybridge configuration from the sambacc config",
    )
    parser.add_argument(
        "--verify-peer",
        action="store_true",
        help="Enable peer process verification",
    )
    parser.add_argument(
        "--peer-check-pid",
        type=_pcheck,
        help=(
            "Verify peers with given PIDs. Supply ints, ranges (<n0>-<nX>),"
            " or comma separated lists (<n0>,<n1>,<n2>...)"
        ),
    )
    parser.add_argument(
        "--peer-check-uid",
        type=_pcheck,
        help=(
            "Verify peers with given UIDs. Supply ints, ranges (<n0>-<nX>),"
            " or comma separated lists (<n0>,<n1>,<n2>...)"
        ),
    )
    parser.add_argument(
        "--peer-check-gid",
        type=_pcheck,
        help=(
            "Verify peers with given GIDs. Supply ints, ranges (<n0>-<nX>),"
            " or comma separated lists (<n0>,<n1>,<n2>...)"
        ),
    )
    parser.add_argument(
        "--mem-scope",
        action="store_true",
        help="Enable keybridge in-memory scope (FOR TESTING ONLY)",
    )
    parser.add_argument(
        "--kmip-scope",
        action="store_true",
        help="Enable KMIP proxy scope",
    )
    parser.add_argument(
        "--kmip-port",
        type=int,
        help="KMIP server port",
    )
    parser.add_argument(
        "--kmip-host",
        dest="kmip_hosts",
        action="append",
        help="KMIP server address",
    )
    parser.add_argument(
        "--kmip-tls-cert",
        help="KMIP TLS server certificate",
    )
    parser.add_argument(
        "--kmip-tls-key",
        help="KMIP TLS server key",
    )
    parser.add_argument(
        "--kmip-tls-ca-cert",
        help="KMIP TLS CA certificate",
    )
    parser.add_argument(
        "address",
        type=_varlink_addr,
        help="Specify a unix:{path} value to bind to.",
    )


def _varlink_addr(value: str) -> str:
    if value.startswith("unix:"):
        return value
    raise argparse.ArgumentTypeError(
        "socket name must be prefixed with 'unix:'"
    )


class Restart(Exception):
    pass


@commands.command(name="keybridge", arg_func=_serve_args)
def serve_keybridge(ctx: Context) -> None:
    """Start a keybridge varlink RPC server."""

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
    import sambacc.varlink.keybridge
    import sambacc.varlink.server

    cfg = ctx.instance_config.keybridge_config(name=ctx.cli.config_section)
    if not cfg:
        cfg = sambacc.config.KeyBridgeConfig({})
    if ctx.cli.mem_scope:
        cfg.update_mem_scope()
    if (
        ctx.cli.kmip_scope
        or ctx.cli.kmip_tls_cert
        or ctx.cli.kmip_tls_key
        or ctx.cli.kmip_tls_ca_cert
    ):
        try:
            cfg.update_kmip_scope(
                ctx.cli.kmip_hosts,
                ctx.cli.kmip_port,
                ctx.cli.kmip_tls_cert,
                ctx.cli.kmip_tls_key,
                ctx.cli.kmip_tls_ca_cert,
            )
        except ValueError as err:
            raise Fail(str(err))

    scopes = [_new_scope(ctx, s) for s in cfg.scopes()]
    vcfg = cfg.verify()
    if ctx.cli.verify_peer or vcfg:
        scopes = [_verify_peer(ctx, vcfg, s) for s in scopes]
    if not scopes:
        raise Fail("no keybridge scopes defined")

    sambacc.varlink.server.patch_varlink_encoder()
    opts = sambacc.varlink.server.VarlinkServerOptions(ctx.cli.address)
    srv = sambacc.varlink.server.VarlinkServer(opts)
    srv.add_endpoint(sambacc.varlink.keybridge.endpoint(scopes))
    _clean_socket_file(ctx.cli.address)
    with srv.serve():
        signal.pause()


def _clean_socket_file(address: str) -> None:
    """Remove the old socket file. I think the lib has fixed this in
    as-yet-unreleased code, but right now every time you start the server when
    the file exists it fails (but then removes the socket) and so without this
    cleanup it always needs to be started twice.
    """
    assert address.startswith("unix:")
    path = pathlib.Path(address.split(":", 1)[-1])
    path.unlink(missing_ok=True)


def _new_scope(
    ctx: Context, scope_cfg: sambacc.config.KeyBridgeScopeConfig
) -> Scope:

    if scope_cfg.type_name == "mem":
        return sambacc.varlink.keybridge.MemScope()
    elif scope_cfg.type_name == "kmip":
        return _kmip_scope(ctx, scope_cfg)
    else:
        raise ValueError(f"invalid scope type name: {scope_cfg.type_name!r}")


def _kmip_scope(
    ctx: Context, scope_cfg: sambacc.config.KeyBridgeScopeConfig
) -> Scope:
    import sambacc.kmip.scope

    if not scope_cfg.hostnames:
        raise Fail("KMIP Store requires at least one KMIP host")
    if not scope_cfg.port or scope_cfg.port < 0:
        raise Fail("KMIP Store requires a KMIP port")
    tls = scope_cfg.tls_paths
    if not tls or not all(tls[k] for k in ("cert", "key", "ca_cert")):
        raise Fail(
            "KMIP Store requires TLS certificate, key, and CA certificate"
        )

    return sambacc.kmip.scope.KMIPScope(
        scope_cfg.subname,
        hosts=scope_cfg.host_ports,
        tls_paths=sambacc.kmip.scope.TLSPaths(**tls),
    )


def _verify_peer(
    ctx: Context,
    vcfg: typing.Optional[sambacc.config.KeyBridgeVerifyConfig],
    scope: Scope,
) -> Scope:
    import sambacc.varlink.keybridge

    if ctx.cli.peer_check_pid:
        check_pid = ctx.cli.peer_check_pid
    elif vcfg and vcfg.check_pid:
        check_pid = vcfg.check_pid
    else:
        check_pid = None
    if ctx.cli.peer_check_uid:
        check_uid = ctx.cli.peer_check_uid
    elif vcfg and vcfg.check_uid:
        check_uid = vcfg.check_uid
    else:
        check_uid = None
    if ctx.cli.peer_check_gid:
        check_gid = ctx.cli.peer_check_gid
    elif vcfg and vcfg.check_gid:
        check_gid = vcfg.check_gid
    else:
        check_gid = None

    return sambacc.varlink.keybridge.VerifyPeerScopeWrapper(
        scope,
        check_pid=check_pid,
        check_uid=check_uid,
        check_gid=check_gid,
    )


def _pcheck(
    value: typing.Optional[str],
) -> typing.Union[None, range, typing.Collection[int]]:
    try:
        return sambacc.config.KeyBridgeVerifyConfig.parameter(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from err
