#
# sambacc: a samba container configuration tool
# Copyright (C) 2021  John Mulligan
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

import typing

from sambacc.typelets import ExcType, ExcValue, ExcTraceback


class LeaderStatus(typing.Protocol):
    """Fetches information about the current cluster leader."""

    def is_leader(self) -> bool:
        """Return true if the current node is the leader."""
        ...  # pragma: no cover


class LeaderLocator(typing.Protocol):
    """Acquire state needed to determine or fix a cluster leader.
    Can be used for purely informational types or types that
    actually acquire cluster leadership if needed.
    """

    def __enter__(self) -> LeaderStatus:
        """Enter context manager. Returns LeaderStatus."""
        ...  # pragma: no cover

    def __exit__(
        self, exc_type: ExcType, exc_val: ExcValue, exc_tb: ExcTraceback
    ) -> bool:
        """Exit context manager."""
        ...  # pragma: no cover
