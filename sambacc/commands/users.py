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

import sambacc.passdb_loader as passdb
import sambacc.passwd_loader as ugl

from .cli import commands, setup_steps, Context


@commands.command(name="import-users")
def import_users(ctx: Context) -> None:
    """Import users and groups from the sambacc config to the passwd
    and group files to support local (non-domain based) login.
    """
    import_sys_users(ctx)
    import_passdb_users(ctx)


@setup_steps.command("users")
def import_sys_users(ctx: Context) -> None:
    """Import users and groups from sambacc config to the passwd and
    group files.
    """
    etc_passwd_loader = ugl.PasswdFileLoader(ctx.cli.etc_passwd_path)
    etc_group_loader = ugl.GroupFileLoader(ctx.cli.etc_group_path)

    etc_passwd_loader.read()
    etc_group_loader.read()
    for u in ctx.instance_config.users():
        etc_passwd_loader.add_user(u)
    for g in ctx.instance_config.groups():
        etc_group_loader.add_group(g)
    etc_passwd_loader.write()
    etc_group_loader.write()


@setup_steps.command("users_passdb")
def import_passdb_users(ctx: Context) -> None:
    """Import users into samba's passdb."""
    smb_passdb_loader = passdb.PassDBLoader()
    for u in ctx.instance_config.users():
        smb_passdb_loader.add_user(u)
    return
