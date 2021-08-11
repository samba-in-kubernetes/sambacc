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

from sambacc import ctdb
import sambacc.nsswitch_loader as nsswitch

from .cli import commands, Context
from .config import import_config
from .users import import_sys_users, import_passdb_users


def _import_nsswitch(ctx: Context) -> None:
    # should nsswitch validation/edit be conditional only on ads?
    nss = nsswitch.NameServiceSwitchLoader("/etc/nsswitch.conf")
    nss.read()
    if not nss.winbind_enabled():
        nss.ensure_winbind_enabled()
        nss.write()


def _smb_conf_for_ctdb(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        print("Enabling ctdb in samba config file")
        ctdb.ensure_smb_conf(ctx.instance_config)


def _ctdb_conf_for_ctdb(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        print("Ensuring ctdb config")
        ctdb.ensure_ctdb_conf(ctx.instance_config)


def _ctdb_nodes_exists(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        print("Ensuring ctdb nodes file")
        persistent_path = ctx.instance_config.ctdb_config()["nodes_path"]
        ctdb.ensure_ctdb_nodes(
            ctdb_nodes=ctdb.read_ctdb_nodes(persistent_path),
            real_path=persistent_path,
        )


def _ctdb_etc_files(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        print("Ensuring ctdb etc files")
        ctdb.ensure_ctdbd_etc_files()


_setup_steps = [
    ("config", import_config),
    ("users", import_sys_users),
    ("smb_ctdb", _smb_conf_for_ctdb),
    ("users_passdb", import_passdb_users),
    ("nsswitch", _import_nsswitch),
    ("ctdb_config", _ctdb_conf_for_ctdb),
    ("ctdb_etc", _ctdb_etc_files),
    ("ctdb_nodes", _ctdb_nodes_exists),
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
