#
# sambacc: a samba container configuration tool
# Copyright (C) 2022  John Mulligan
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
"""typelets defines common-ish type hinting types that are tedious to
remember/redefine.
"""

from types import TracebackType
import sys
import typing

ExcType = typing.Optional[typing.Type[BaseException]]
ExcValue = typing.Optional[BaseException]
ExcTraceback = typing.Optional[TracebackType]


if sys.version_info >= (3, 11):
    from typing import Self
elif typing.TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self = typing.Any
