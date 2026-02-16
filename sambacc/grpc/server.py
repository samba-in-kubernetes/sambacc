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

from typing import Any, Callable, Iterator, Protocol, Optional, cast

import concurrent.futures
import contextlib
import hashlib
import logging

import grpc

import sambacc.grpc.backend as rbe
import sambacc.grpc.generated.control_pb2 as pb
import sambacc.grpc.generated.control_pb2_grpc as control_rpc

from sambacc.grpc.config import ConnectionConfig, ServerConfig


_logger = logging.getLogger(__name__)


class Backend(Protocol):
    def get_versions(self) -> rbe.Versions: ...

    def is_clustered(self) -> bool: ...

    def get_status(self) -> rbe.Status: ...

    def close_share(self, share_name: str, denied_users: bool) -> None: ...

    def kill_client(self, ip_address: str) -> None: ...

    def config_dump(
        self, src: rbe.ConfigFor, hash_alg: Optional[Callable]
    ) -> Iterator[rbe.DumpItem]: ...

    def config_dump_digest(
        self, src: rbe.ConfigFor, hash_alg: Optional[Callable]
    ) -> rbe.DumpItem: ...

    def config_share_list(
        self, src: rbe.ConfigFor
    ) -> Iterator[rbe.ShareEntry]: ...

    def set_debug_level(
        self, server: rbe.ServerType, debug_level: str
    ) -> None: ...

    def get_debug_level(self, server: rbe.ServerType) -> str: ...


@contextlib.contextmanager
def _in_rpc(context: grpc.ServicerContext, allowed: bool) -> Iterator[None]:
    if not allowed:
        _logger.error("Blocking operation")
        context.abort(
            grpc.StatusCode.PERMISSION_DENIED, "Operation not permitted"
        )
    try:
        yield
    except NotImplementedError as err:
        _logger.exception("exception in rpc call")
        context.abort(grpc.StatusCode.UNIMPLEMENTED, f"not implemented: {err}")
    except FileNotFoundError as err:
        _logger.exception("exception in rpc call")
        context.abort(grpc.StatusCode.NOT_FOUND, f"not found: {err}")
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


def _config_source(src_opt: pb.ConfigFor) -> rbe.ConfigFor:
    opts: dict[Any, rbe.ConfigFor] = {
        pb.CONFIG_FOR_SAMBA: rbe.ConfigFor.SAMBA,
        pb.CONFIG_FOR_CTDB: rbe.ConfigFor.CTDB,
        pb.CONFIG_FOR_SAMBACC: rbe.ConfigFor.SAMBACC,
    }
    try:
        return opts[src_opt]
    except KeyError:
        raise ValueError("invalid configuration source")


def _pick_hash(
    hash_opt: pb.HashAlg, default: Optional[Callable]
) -> Optional[Callable]:
    opts: dict[Any, Callable] = {
        pb.HASH_ALG_SHA256: hashlib.sha256,
    }
    return opts.get(hash_opt, default)


def _server_type(process: pb.SMBProcess) -> rbe.ServerType:
    opts: dict[Any, rbe.ServerType] = {
        pb.SMB_PROCESS_SMB: rbe.ServerType.SMB,
        pb.SMB_PROCESS_WINBIND: rbe.ServerType.WINBIND,
        pb.SMB_PROCESS_CTDB: rbe.ServerType.CTDB,
    }
    try:
        return opts[process]
    except KeyError:
        raise ValueError(f"invalid smb process type: {process!r}")


class ControlService(control_rpc.SambaControlServicer):
    def __init__(self, backend: Backend, *, read_only: bool = False):
        self._backend = backend
        self._read_only = read_only
        self._ok_to_read = True
        self._ok_to_modify = not read_only

    @property
    def _ok_to_diag(self) -> bool:
        # Acts as lias for _ok_to_read.
        return self._ok_to_read

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

    def ConfigDump(
        self, request: pb.ConfigDumpRequest, context: grpc.ServicerContext
    ) -> Iterator[pb.ConfigDumpItem]:
        _logger.debug("RPC Called: ConfigDump")
        with _in_rpc(context, self._ok_to_diag):
            src = _config_source(cast(pb.ConfigFor, request.source))
            hash_alg = _pick_hash(cast(pb.HashAlg, request.hash), None)
            for dump_item in self._backend.config_dump(src, hash_alg):
                if dump_item.is_digest():
                    assert dump_item.hash_type == "sha256"
                    yield pb.ConfigDumpItem(
                        digest=pb.ConfigDigest(
                            hash=pb.HASH_ALG_SHA256,
                            config_digest=dump_item.content,
                        )
                    )
                    continue
                yield pb.ConfigDumpItem(
                    line=pb.ConfigLine(
                        line_number=dump_item.line_number,
                        content=dump_item.content,
                    )
                )

    def ConfigSummary(
        self, request: pb.ConfigSummaryRequest, context: grpc.ServicerContext
    ) -> pb.ConfigSummaryInfo:
        _logger.debug("RPC Called: ConfigSummary")
        with _in_rpc(context, self._ok_to_diag):
            src = _config_source(cast(pb.ConfigFor, request.source))
            hash_alg = _pick_hash(
                cast(pb.HashAlg, request.hash), hashlib.sha256
            )
            dump_item = self._backend.config_dump_digest(src, hash_alg)
            assert dump_item.is_digest()
            assert dump_item.hash_type == "sha256"
            return pb.ConfigSummaryInfo(
                source=request.source,
                digest=pb.ConfigDigest(
                    hash=pb.HASH_ALG_SHA256,
                    config_digest=dump_item.content,
                ),
            )

    def ConfigSharesList(
        self,
        request: pb.ConfigSharesListRequest,
        context: grpc.ServicerContext,
    ) -> Iterator[pb.ConfigShareItem]:
        _logger.debug("RPC Called: ConfigSharesList")
        with _in_rpc(context, self._ok_to_diag):
            src = _config_source(cast(pb.ConfigFor, request.source))
            for share in self._backend.config_share_list(src):
                yield pb.ConfigShareItem(name=share.name)

    def SetDebugLevel(
        self, request: pb.SetDebugLevelRequest, context: grpc.ServicerContext
    ) -> pb.DebugLevelInfo:
        _logger.debug("RPC Called: SetDebugLevel")
        with _in_rpc(context, self._ok_to_modify):
            server = _server_type(cast(pb.SMBProcess, request.process))
            debug_level = request.debug_level
            self._backend.set_debug_level(server, debug_level)
            # round trip for clarity
            info = pb.DebugLevelInfo(
                process=request.process,
                debug_level=debug_level,
            )
        return info

    def GetDebugLevel(
        self, request: pb.GetDebugLevelRequest, context: grpc.ServicerContext
    ) -> pb.DebugLevelInfo:
        _logger.debug("RPC Called: GetDebugLevel")
        with _in_rpc(context, self._ok_to_read):
            server = _server_type(cast(pb.SMBProcess, request.process))
            debug_level = self._backend.get_debug_level(server)
            info = pb.DebugLevelInfo(
                process=request.process,
                debug_level=debug_level,
            )
        return info


def _add_port(server: grpc.Server, config: ConnectionConfig) -> None:
    _logger.info(
        "Adding gRPC port on %s (%s)", config.address, config.describe()
    )
    if config.insecure:
        server.add_insecure_port(config.address)
        return

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


def serve(config: ServerConfig, backend: Backend) -> None:
    if not config.connections:
        raise ValueError("no connections in server config")
    _logger.info(
        "Starting gRPC server (%s mode)",
        "read-only" if config.read_only else "read-modify",
    )
    service = ControlService(backend, read_only=config.read_only)
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=config.max_workers
    )
    server = grpc.server(executor)
    control_rpc.add_SambaControlServicer_to_server(service, server)
    for conn in config.connections:
        _add_port(server, conn)
    server.start()
    # hack for testing
    wait_fn = getattr(config, "wait", None)
    if wait_fn:
        wait_fn(server)
    else:
        server.wait_for_termination()
