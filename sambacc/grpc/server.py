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

from typing import Iterator, Protocol, Optional

import concurrent.futures
import contextlib
import logging

import grpc

import sambacc.grpc.backend as rbe
import sambacc.grpc.generated.control_pb2 as pb
import sambacc.grpc.generated.control_pb2_grpc as control_rpc

_logger = logging.getLogger(__name__)


class Backend(Protocol):
    def get_versions(self) -> rbe.Versions: ...

    def is_clustered(self) -> bool: ...

    def get_status(self) -> rbe.Status: ...

    def close_share(self, share_name: str, denied_users: bool) -> None: ...

    def kill_client(self, ip_address: str) -> None: ...


@contextlib.contextmanager
def _in_rpc(context: grpc.ServicerContext, allowed: bool) -> Iterator[None]:
    if not allowed:
        _logger.error("Blocking operation")
        context.abort(
            grpc.StatusCode.PERMISSION_DENIED, "Operation not permitted"
        )
    try:
        yield
    except Exception:
        _logger.exception("exception in rpc call")
        context.abort(grpc.StatusCode.UNKNOWN, "Unexpected server error")


def _get_info(backend: Backend) -> pb.GeneralInfo:
    _info = backend.get_versions()
    clustered = backend.is_clustered()
    return pb.GeneralInfo(
        samba_info=pb.SambaInfo(
            version=_info.samba_version,
            clustered=clustered,
        ),
        container_info=pb.SambaContainerInfo(
            sambacc_version=_info.sambacc_version,
            container_version=_info.container_version,
        ),
    )


def _convert_crypto(
    crypto: Optional[rbe.SessionCrypto],
) -> Optional[pb.SessionCrypto]:
    if not crypto:
        return None
    return pb.SessionCrypto(cipher=crypto.cipher, degree=crypto.degree)


def _convert_session(session: rbe.Session) -> pb.SessionInfo:
    info = pb.SessionInfo(
        session_id=session.session_id,
        username=session.username,
        groupname=session.groupname,
        remote_machine=session.remote_machine,
        hostname=session.hostname,
        session_dialect=session.session_dialect,
        encryption=_convert_crypto(session.encryption),
        signing=_convert_crypto(session.signing),
    )
    # python side takes -1 to mean not found uid/gid. in protobufs
    # that would mean the fields are unset
    if session.uid > 0:
        info.uid = session.uid
    if session.gid > 0:
        info.gid = session.gid
    return info


def _convert_tcon(tcon: rbe.TreeConnection) -> pb.ConnInfo:
    return pb.ConnInfo(
        tcon_id=tcon.tcon_id,
        session_id=tcon.session_id,
        service_name=tcon.service_name,
    )


def _convert_status(status: rbe.Status) -> pb.StatusInfo:
    return pb.StatusInfo(
        server_timestamp=status.timestamp,
        sessions=[_convert_session(s) for s in status.sessions],
        tree_connections=[_convert_tcon(t) for t in status.tcons],
    )


class ControlService(control_rpc.SambaControlServicer):
    def __init__(self, backend: Backend, *, read_only: bool = False):
        self._backend = backend
        self._read_only = read_only
        self._ok_to_read = True
        self._ok_to_modify = not read_only

    def Info(
        self, request: pb.InfoRequest, context: grpc.ServicerContext
    ) -> pb.GeneralInfo:
        _logger.debug("RPC Called: Info")
        with _in_rpc(context, self._ok_to_read):
            info = _get_info(self._backend)
        return info

    def Status(
        self, request: pb.StatusRequest, context: grpc.ServicerContext
    ) -> pb.StatusInfo:
        _logger.debug("RPC Called: Status")
        with _in_rpc(context, self._ok_to_read):
            info = _convert_status(self._backend.get_status())
        return info

    def CloseShare(
        self, request: pb.CloseShareRequest, context: grpc.ServicerContext
    ) -> pb.CloseShareInfo:
        _logger.debug("RPC Called: CloseShare")
        with _in_rpc(context, self._ok_to_modify):
            self._backend.close_share(request.share_name, request.denied_users)
            info = pb.CloseShareInfo()
        return info

    def KillClientConnection(
        self, request: pb.KillClientRequest, context: grpc.ServicerContext
    ) -> pb.KillClientInfo:
        _logger.debug("RPC Called: KillClientConnection")
        with _in_rpc(context, self._ok_to_modify):
            self._backend.kill_client(request.ip_address)
            info = pb.KillClientInfo()
        return info


class ServerConfig:
    max_workers: int = 8
    address: str = "localhost:54445"
    read_only: bool = False
    insecure: bool = True
    server_key: Optional[bytes] = None
    server_cert: Optional[bytes] = None
    ca_cert: Optional[bytes] = None


def serve(config: ServerConfig, backend: Backend) -> None:
    _logger.info(
        "Starting gRPC server on %s (%s, %s)",
        config.address,
        "insecure" if config.insecure else "tls",
        "read-only" if config.read_only else "read-modify",
    )
    service = ControlService(backend, read_only=config.read_only)
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=config.max_workers
    )
    server = grpc.server(executor)
    control_rpc.add_SambaControlServicer_to_server(service, server)
    if config.insecure:
        server.add_insecure_port(config.address)
    else:
        if not config.server_key:
            raise ValueError("missing server TLS key")
        if not config.server_cert:
            raise ValueError("missing server TLS cert")
        if config.ca_cert:
            creds = grpc.ssl_server_credentials(
                [(config.server_key, config.server_cert)],
                root_certificates=config.ca_cert,
                require_client_auth=True,
            )
        else:
            creds = grpc.ssl_server_credentials(
                [(config.server_key, config.server_cert)],
            )
        server.add_secure_port(config.address, creds)
    server.start()
    # hack for testing
    wait_fn = getattr(config, "wait", None)
    if wait_fn:
        wait_fn(server)
    else:
        server.wait_for_termination()
