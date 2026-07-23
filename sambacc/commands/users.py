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
from sambacc import config
from sambacc import paths

from .cli import commands, setup_steps, Context, AltLocation


def sync_sys_users(
    iconfig: config.InstanceConfig,
    passwd_location: AltLocation,
    group_location: AltLocation,
) -> None:
    """Import users and groups from an InstanceConfig to the passwd and
    group files.
    """
    etc_passwd_loader = ugl.PasswdFileLoader(passwd_location.writable)
    etc_group_loader = ugl.GroupFileLoader(group_location.writable)
    etc_passwd_loader.read()
    etc_group_loader.read()
    for u in iconfig.users():
        etc_passwd_loader.add_user(u)
    for g in iconfig.groups():
        etc_group_loader.add_group(g)
    etc_passwd_loader.write()
    etc_group_loader.write()

    # let os errors bubble up here. we want to stop if we can't create these
    # necessary links
    if passwd_location.link_path:
        paths.ensure_symlink(
            passwd_location.writable, passwd_location.link_path
        )
    if group_location.link_path:
        paths.ensure_symlink(group_location.writable, group_location.link_path)


def sync_passdb_users(iconfig: config.InstanceConfig) -> None:
    """Import users into samba's passdb."""
    smb_passdb_loader = passdb.PassDBLoader()
    for u in iconfig.users():
        smb_passdb_loader.add_user(u)


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
    sync_sys_users(
        ctx.instance_config,
        ctx.cli.passwd_location,
        ctx.cli.group_location,
    )


@setup_steps.command("users_passdb")
def import_passdb_users(ctx: Context) -> None:
    """Import users into samba's passdb."""
    sync_passdb_users(ctx.instance_config)
