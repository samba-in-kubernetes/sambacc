#
# sambacc: a samba container configuration tool (and more)
# Copyright (C) 2026  John Mulligan
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

from typing import Optional

import sambacc.grpc.backend as rbe
import sambacc.grpc.generated.control_pb2 as pb


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


def status(status: rbe.Status) -> pb.StatusInfo:
    return pb.StatusInfo(
        server_timestamp=status.timestamp,
        sessions=[_convert_session(s) for s in status.sessions],
        tree_connections=[_convert_tcon(t) for t in status.tcons],
    )


def _ctdb_node(node: rbe.CTDBNode) -> pb.CTDBNodeInfo:
    return pb.CTDBNodeInfo(
        pnn=node.pnn,
        address=node.address,
        partially_online=node.partially_online,
        flags_raw=node.flags_raw,
        flags=node.flags,
        this_node=node.this_node,
    )


def _ctdb_node_status(ns: rbe.CTDBNodeStatus) -> pb.CTDBNodeStatus:
    return pb.CTDBNodeStatus(
        node_count=ns.node_count,
        deleted_node_count=ns.deleted_node_count,
        nodes=[_ctdb_node(n) for n in ns.nodes],
    )


def _ctdb_vnn_status(vs: rbe.CTDBVNNStatus) -> pb.CTDBVNNStatus:
    return pb.CTDBVNNStatus(
        generation=vs.generation,
        size=vs.size,
        vnn_map=[
            pb.VNNInfo(hash=v.hash, lmaster=v.lmaster) for v in vs.vnn_map
        ],
    )


def _ctdb_ip_location(loc: rbe.CTDBIPLocation) -> pb.CTDBIPLocation:
    return pb.CTDBIPLocation(
        address=loc.address,
        node=loc.node,
    )


def ctdb_status(status: rbe.CTDBStatus) -> pb.CTDBStatusInfo:
    return pb.CTDBStatusInfo(
        node_status=_ctdb_node_status(status.node_status),
        vnn_status=_ctdb_vnn_status(status.vnn_status),
        recovery_mode=status.recovery_mode,
        recovery_mode_raw=status.recovery_mode_raw,
        leader=status.leader,
        ips=[_ctdb_ip_location(loc) for loc in status.ips],
    )


def _cluster_level(
    level: Optional[rbe.ClusterFunctionalLevel],
) -> Optional[pb.ClusterFunctionalLevel]:
    if level is None:
        return None
    return pb.ClusterFunctionalLevel(major=level.major, minor=level.minor)


def _cluster_level_range(r: rbe.ClusterLevelRange) -> pb.ClusterLevelRange:
    return pb.ClusterLevelRange(
        major=r.major, minor_min=r.minor_min, minor_max=r.minor_max
    )


def _cluster_level_node(n: rbe.ClusterLevelNode) -> pb.ClusterLevelNode:
    return pb.ClusterLevelNode(
        pnn=n.pnn,
        supported_ranges=[_cluster_level_range(r) for r in n.supported_ranges],
    )


def active_cluster_level(
    level: rbe.ClusterFunctionalLevel,
) -> pb.ClusterFunctionalLevel:
    return pb.ClusterFunctionalLevel(major=level.major, minor=level.minor)


def cluster_level_info(info: rbe.ClusterLevelInfo) -> pb.ClusterLevelInfo:
    return pb.ClusterLevelInfo(
        active_level=_cluster_level(info.active_level),
        nodes=[_cluster_level_node(n) for n in info.nodes],
        upgrade_possible=info.upgrade_possible,
        highest_level=_cluster_level(info.highest_level),
    )


_CLUSTER_LEVEL_UPGRADE_STATUS = {
    "already_current": pb.CLUSTER_LEVEL_UPGRADE_STATUS_ALREADY_CURRENT,
    "dry_run_ok": pb.CLUSTER_LEVEL_UPGRADE_STATUS_DRY_RUN_OK,
    "upgraded": pb.CLUSTER_LEVEL_UPGRADE_STATUS_UPGRADED,
    "error": pb.CLUSTER_LEVEL_UPGRADE_STATUS_ERROR,
}


def cluster_level_upgrade_result(
    result: rbe.ClusterLevelUpgradeResult,
) -> pb.UpgradeClusterLevelInfo:
    status = _CLUSTER_LEVEL_UPGRADE_STATUS.get(
        result.status, pb.CLUSTER_LEVEL_UPGRADE_STATUS_UNKNOWN
    )
    unknown = status == pb.CLUSTER_LEVEL_UPGRADE_STATUS_UNKNOWN
    return pb.UpgradeClusterLevelInfo(
        dry_run=result.dry_run,
        status=status,
        unknown_status=result.status if unknown else "",
        old_level=_cluster_level(result.old_level),
        new_level=_cluster_level(result.new_level),
        error_vnn=result.error_vnn or 0,
        error_status=result.error_status or "",
    )


def cluster_level_features(
    features: rbe.ClusterLevelFeatures,
) -> pb.ClusterLevelFeaturesInfo:
    return pb.ClusterLevelFeaturesInfo(
        cluster_support=features.cluster_support,
        ctdb_socket=features.ctdb_socket,
        ctdb_protocol=features.ctdb_protocol,
        supported_ranges=[
            _cluster_level_range(r) for r in features.supported_ranges
        ],
    )
