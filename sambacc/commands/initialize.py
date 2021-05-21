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

import sambacc.nsswitch_loader as nsswitch

from .cli import commands
from .config import import_config
from .users import import_users


@commands.command(name="init")
def init_container(cli, config):
    """Initialize the entire container environment."""
    import_config(cli, config)
    import_users(cli, config)

    # should nsswitch validation/edit be conditional only on ads?
    nss = nsswitch.NameServiceSwitchLoader("/etc/nsswitch.conf")
    nss.read()
    if not nss.winbind_enabled():
        nss.ensure_winbind_enabled()
        nss.write()
