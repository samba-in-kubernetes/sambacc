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

from typing import (
    Any,
    Callable,
    Collection,
    Iterator,
    Optional,
    Protocol,
    cast,
)

import concurrent.futures
import contextlib
import hashlib
import logging

import grpc

import sambacc.grpc.backend as rbe
import sambacc.grpc.conversions as rcv
import sambacc.grpc.generated.control_pb2 as pb
import sambacc.grpc.generated.control_pb2_grpc as control_rpc

from sambacc.grpc.config import (
    ClientVerification,
    ConnectionConfig,
    Level,
    MagicTokenConfig,
    RADOSCheckerConfig,
    ServerConfig,
)


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


class ClientChecker(Protocol):
    def allowed_client(
        self, level: Level, context: grpc.ServicerContext
    ) -> bool: ...


@contextlib.contextmanager
def _catch_rpc(context: grpc.ServicerContext) -> Iterator[None]:
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


@contextlib.contextmanager
def _checked_rpc(
    context: grpc.ServicerContext,
    *,
    name: str,
    required_level: Level,
    checker: ClientChecker,
) -> Iterator[None]:
    _logger.debug("RPC Called: %s", name)

    if not checker.allowed_client(required_level, context):
        _logger.error("Blocking client %s for %s rpc", context.peer(), name)
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "Client not permitted")

    with _catch_rpc(context):
        yield


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


class LevelClientChecker:
    def __init__(self, *levels: Level, enable_all: bool = False) -> None:
        self._levels = set(Level) if enable_all else set(levels)
        assert self._levels, "no levels set for LevelClientChecker"

    def allowed_client(
        self, level: Level, context: grpc.ServicerContext
    ) -> bool:
        ok = level in self._levels
        _logger.debug(
            "default client checker (for %s): %r in %s: %s",
            context.peer(),
            level,
            self._levels,
            ok,
        )
        return ok


class TLSClientChecker:
    def allowed_client(
        self, level: Level, context: grpc.ServicerContext
    ) -> bool:
        actx = context.auth_context()
        tstype = actx.get("transport_security_type")
        if tstype and b"ssl" in tstype:
            _logger.debug("Client is using (m)TLS")
            return True
        return False


class MagicTokenClientChecker:
    """Static ENV based token checker. *Do not use in production.*
    For development and examples only.
    """

    def __init__(self, config: MagicTokenConfig) -> None:
        import os

        self._env_var = config.env_var
        self._key = config.header_key

        self.value = os.environ.get(self._env_var)
        if not self.value:
            _logger.warning(
                "MagicTokenClientChecker enabled but %s not set",
                self._env_var,
            )
            return
        _logger.info("MAGIC: %s", self.value)

    def allowed_client(
        self, level: Level, context: grpc.ServicerContext
    ) -> bool:
        if not self.value:
            return False
        peer = context.peer()
        imeta = context.invocation_metadata()
        if (self._key, self.value) in imeta and peer.startswith("unix:"):
            _logger.debug("Client has magic token")
            return True
        return False


def _rados_checker(config: RADOSCheckerConfig) -> ClientChecker:
    import sambacc.grpc.rados_checker

    return sambacc.grpc.rados_checker.RADOSClientChecker(config)


class ControlService(control_rpc.SambaControlServicer):
    def __init__(
        self,
        backend: Backend,
        *,
        read_only: bool = False,
        client_checkers: Optional[Collection[ClientChecker]] = None,
    ):
        self._backend = backend
        self._allowed_levels = {Level.READ, Level.DEBUG_READ}
        if not read_only:
            self._allowed_levels.add(Level.MODIFY)
        if client_checkers:
            self._client_checkers = list(client_checkers)
        else:
            self._client_checkers = [
                LevelClientChecker(enable_all=True),
            ]

    def allowed_client(
        self, required_level: Level, context: grpc.ServicerContext
    ) -> bool:
        if required_level not in self._allowed_levels:
            _logger.error(
                "Rejecting operation for %s: %s level not allowed",
                context.peer(),
                required_level,
            )
            return False
        return any(
            c.allowed_client(required_level, context)
            for c in self._client_checkers
        )

    def Info(
        self, request: pb.InfoRequest, context: grpc.ServicerContext
    ) -> pb.GeneralInfo:
        with _checked_rpc(
            context, name="Info", required_level=Level.READ, checker=self
        ):
            info = _get_info(self._backend)
        return info

    def Status(
        self, request: pb.StatusRequest, context: grpc.ServicerContext
    ) -> pb.StatusInfo:
        with _checked_rpc(
            context, name="Status", required_level=Level.READ, checker=self
        ):
            info = rcv.status(self._backend.get_status())
        return info

    def CloseShare(
        self, request: pb.CloseShareRequest, context: grpc.ServicerContext
    ) -> pb.CloseShareInfo:
        with _checked_rpc(
            context,
            name="CloseShare",
            required_level=Level.MODIFY,
            checker=self,
        ):
            self._backend.close_share(request.share_name, request.denied_users)
            info = pb.CloseShareInfo()
        return info

    def KillClientConnection(
        self, request: pb.KillClientRequest, context: grpc.ServicerContext
    ) -> pb.KillClientInfo:
        with _checked_rpc(
            context,
            name="KillClientConnection",
            required_level=Level.MODIFY,
            checker=self,
        ):
            self._backend.kill_client(request.ip_address)
            info = pb.KillClientInfo()
        return info

    def ConfigDump(
        self, request: pb.ConfigDumpRequest, context: grpc.ServicerContext
    ) -> Iterator[pb.ConfigDumpItem]:
        with _checked_rpc(
            context,
            name="ConfigDump",
            required_level=Level.DEBUG_READ,
            checker=self,
        ):
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
        with _checked_rpc(
            context,
            name="ConfigSummary",
            required_level=Level.DEBUG_READ,
            checker=self,
        ):
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
        with _checked_rpc(
            context,
            name="ConfigSharesList",
            required_level=Level.DEBUG_READ,
            checker=self,
        ):
            src = _config_source(cast(pb.ConfigFor, request.source))
            for share in self._backend.config_share_list(src):
                yield pb.ConfigShareItem(name=share.name)

    def SetDebugLevel(
        self, request: pb.SetDebugLevelRequest, context: grpc.ServicerContext
    ) -> pb.DebugLevelInfo:
        with _checked_rpc(
            context,
            name="SetDebugLevel",
            required_level=Level.MODIFY,
            checker=self,
        ):
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
        with _checked_rpc(
            context,
            name="GetDebugLevel",
            required_level=Level.READ,
            checker=self,
        ):
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
    if not config.uses_tls:
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


def _checkers(config: ServerConfig) -> Iterator[ClientChecker]:
    """Set up checkers, which are executed in series because grpc
    doesn't really give us a way to bind things to particular channels
    so we just configure a mix of checkers based on our configs.

    For ConnectionConfig objects that need additional configuration
    for a checker it must provide a value in the checker_conf field.
    """
    ccmap: dict[ClientVerification, Callable] = {
        ClientVerification.TOKEN: MagicTokenClientChecker,
        ClientVerification.TLS: TLSClientChecker,
        ClientVerification.RADOS: _rados_checker,
    }
    unhandled = set()
    for cc in config.connections:
        # special care INSECURE
        if (
            cc.verification is ClientVerification.INSECURE
            and not config.read_only
        ):
            yield LevelClientChecker(enable_all=True)
            continue
        # enable normal checkers
        _checker: Optional[Callable] = ccmap.get(cc.verification)
        if not _checker:
            unhandled.add(cc.verification)
            continue
        _args = []
        if cc.checker_conf and cc.checker_conf.can_verify(cc.verification):
            _args = [cc.checker_conf]
        elif cc.checker_conf:
            raise ValueError(f"incorrect config for {cc.verification}")
        yield _checker(*_args)
    if unhandled:
        raise ValueError(f"unhandled verification method(s): {unhandled}")
    yield LevelClientChecker(Level.READ)


def serve(config: ServerConfig, backend: Backend) -> None:
    if not config.connections:
        raise ValueError("no connections in server config")
    _logger.info(
        "Starting gRPC server (%s mode)",
        "read-only" if config.read_only else "read-modify",
    )
    service = ControlService(
        backend,
        read_only=config.read_only,
        client_checkers=list(_checkers(config)),
    )
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
