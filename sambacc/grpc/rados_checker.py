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

import logging

import grpc

import sambacc.ceph.rados
import sambacc.grpc.config


_logger = logging.getLogger(__name__)


def _ceph_parms(
    context: grpc.ServicerContext,
    config: sambacc.grpc.config.RADOSCheckerConfig,
) -> tuple[str, str]:

    imeta = dict(context.invocation_metadata())
    _user = imeta.get(config.header_user, "")
    _key = imeta.get(config.header_key, "")
    return (
        _user if isinstance(_user, str) else _user.decode(),
        _key if isinstance(_key, str) else _key.decode(),
    )


class RADOSClientChecker:
    """Ceph object access checker. Uses ceph key sent thru a secure
    but unauthenticated channel to use verify the ceph object
    can be accessed.
    """

    def __init__(self, config: sambacc.grpc.config.RADOSCheckerConfig) -> None:
        self._config = config
        self._enabled = sambacc.ceph.rados.enable_rados_lib(ignore_error=True)
        if not self._enabled:
            _logger.error(
                "RADOS is not enabled; RADOSClientChecker will be disabled"
            )

    def allowed_client(
        self, level: sambacc.grpc.config.Level, context: grpc.ServicerContext
    ) -> bool:
        if not self._enabled:
            return False

        peer = context.peer()
        ceph_user, ceph_key = _ceph_parms(context, self._config)
        if not (ceph_user and ceph_key):
            _logger.debug("Client %s did not provide ceph user & key", peer)
            return False
        if self._probe(ceph_user, ceph_key):
            _logger.debug("Client %s passed rados access check", peer)
            return True
        _logger.debug("Client %s failed rados access check", peer)
        return False

    def _probe(self, ceph_user: str, ceph_key: str) -> bool:
        rlib = sambacc.ceph.rados.RADOSConnection.library()
        try:
            rconn = sambacc.ceph.rados.RADOSConnection.create(
                conffile=self._config.conffile,
                name=ceph_user,
                key=ceph_key,
            )
            rconn.get_object(self._config.object_uri, must_exist=True)
        except rlib.Error as err:
            _logger.debug("rados check failed: %r", err)
            return False
        return True
