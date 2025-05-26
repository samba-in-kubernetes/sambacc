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


import typing


class VarlinkEndpoint:
    """The sambacc VarlinkEndpoint classes are used to connect the varlink
    server to the backend logic. It must provide the varlink interface as well
    as the implementation class and that class's (keyword) arguments.
    """

    location: str = "sambacc.varlink.interfaces"
    interface_filename: str = ""
    interface_name: str = ""
    interface_cls: typing.Type
    interface_kwargs: dict

    def __init__(
        self,
        *,
        location: str = "",
        interface_filename: str = "",
        interface_name: str = "",
        interface_cls: typing.Optional[typing.Type] = None,
        interface_kwargs: typing.Optional[dict] = None,
    ) -> None:
        if location:
            self.location = location
        if interface_filename:
            self.interface_filename = interface_filename
        if interface_name:
            self.interface_name = interface_name
        if interface_cls:
            self.interface_cls = interface_cls
        else:
            raise ValueError("an interface class is required")
        if interface_kwargs:
            self.interface_kwargs = interface_kwargs
        else:
            self.interface_kwargs = {}
