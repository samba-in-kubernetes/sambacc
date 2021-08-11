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

from .cli import commands, Context
from .config import import_config
from .users import import_users


def _import_nsswitch(ctx: Context) -> None:
    # should nsswitch validation/edit be conditional only on ads?
    nss = nsswitch.NameServiceSwitchLoader("/etc/nsswitch.conf")
    nss.read()
    if not nss.winbind_enabled():
        nss.ensure_winbind_enabled()
        nss.write()


_setup_steps = [
    ("config", import_config),
    ("users", import_users),
    ("nsswitch", _import_nsswitch),
]


def setup_step_names():
    """Return a list of names for the steps that init supports."""
    return [s[0] for s in _setup_steps]


@commands.command(name="init")
def init_container(ctx: Context, steps=None) -> None:
    """Initialize the entire container environment."""
    for name, setup_func in _setup_steps:
        if steps and name not in steps:
            continue
        setup_func(ctx)
