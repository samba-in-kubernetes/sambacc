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
"""xattr shim module

This module exists to insulate sambacc from the platform xattr module.
Currently it only support pyxattr. This module can be imported without
pyxattr (xattr) present. The functions will import the required module
and raise an ImportError if xattr is not available.

This shim also provides a typed functions for xattr management. This
could have been accomplished by writing a pyi file for xattr but since
we need the runtime support we just add new functions.
"""


import pathlib
import typing

XAttrItem = typing.Union[
    int,  # an open file descriptor, not wrapped by an object
    pathlib.Path,  # pathlib path object
    str,  # basic path string
    typing.IO,  # an open file descriptor, wrapped by an object
]
Namespace = typing.Optional[bytes]


def get(
    item: XAttrItem,
    name: str,
    *,
    nofollow: bool = False,
    namespace: Namespace = None
) -> bytes:
    """Get an xattr from the target item and name.
    See docs for PyXattr module for details.
    """
    import xattr  # type: ignore

    kwargs: dict[str, typing.Any] = {"nofollow": nofollow}
    if namespace is not None:
        kwargs["namespace"] = namespace
    return xattr.get(item, name, **kwargs)


def set(
    item: XAttrItem,
    name: str,
    value: str,
    *,
    flags: typing.Optional[int] = None,
    nofollow: bool = False,
    namespace: Namespace = None
) -> None:
    """Set an xattr. See docs for PyXattr module for details."""
    import xattr  # type: ignore

    kwargs: dict[str, typing.Any] = {"nofollow": nofollow}
    if flags is not None:
        kwargs["flags"] = flags
    if namespace is not None:
        kwargs["namespace"] = namespace
    return xattr.set(item, name, value, **kwargs)
