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

import logging
import typing

from sambacc import ctdb
from sambacc import paths
import sambacc.nsswitch_loader as nsswitch

from . import config  # noqa: F401
from . import users  # noqa: F401
from .cli import commands, perms_handler, setup_steps, Context


_logger = logging.getLogger(__name__)


@setup_steps.command("nsswitch")
def _import_nsswitch(ctx: Context) -> None:
    # should nsswitch validation/edit be conditional only on ads?
    nss = nsswitch.NameServiceSwitchLoader("/etc/nsswitch.conf")
    nss.read()
    if not nss.winbind_enabled():
        nss.ensure_winbind_enabled()
        nss.write()


@setup_steps.command("smb_ctdb")
def _smb_conf_for_ctdb(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        _logger.info("Enabling ctdb in samba config file")
        ctdb.ensure_smb_conf(ctx.instance_config)


@setup_steps.command("ctdb_config")
def _ctdb_conf_for_ctdb(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        _logger.info("Ensuring ctdb config")
        ctdb.ensure_ctdb_conf(ctx.instance_config)


@setup_steps.command("ctdb_nodes")
def _ctdb_nodes_exists(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        _logger.info("Ensuring ctdb nodes file")
        persistent_path = ctx.instance_config.ctdb_config()["nodes_path"]
        ctdb.ensure_ctdb_nodes(
            ctdb_nodes=ctdb.read_ctdb_nodes(persistent_path),
            real_path=persistent_path,
        )


@setup_steps.command("ctdb_etc")
def _ctdb_etc_files(ctx: Context) -> None:
    if ctx.instance_config.with_ctdb and ctx.expects_ctdb:
        _logger.info("Ensuring ctdb etc files")
        ctdb.ensure_ctdbd_etc_files(iconfig=ctx.instance_config)


@setup_steps.command("share_paths")
@commands.command(name="ensure-share-paths")
def ensure_share_paths(ctx: Context) -> None:
    """Ensure the paths defined by the configuration exist."""
    # currently this is completely ignorant of things like vfs
    # modules that might "virtualize" the share path. It just
    # assumes that the path in the configuration is an absolute
    # path in the file system.
    for share in ctx.instance_config.shares():
        path = share.path()
        if not path:
            continue
        _logger.info(f"Ensuring share path: {path}")
        paths.ensure_share_dirs(path)
        _logger.info(f"Updating permissions if needed: {path}")
        perms_handler(share.permissions_config(), path).update()


_default_setup_steps = [
    "config",
    "users",
    "smb_ctdb",
    "users_passdb",
    "nsswitch",
]


def setup_step_names():
    """Return a list of names for the steps that init supports."""
    return list(setup_steps.dict().keys())


@commands.command(name="init")
def init_container(
    ctx: Context, steps: typing.Optional[typing.Iterable[str]] = None
) -> None:
    """Initialize the entire container environment."""
    steps = _default_setup_steps if steps is None else list(steps)
    cmds = setup_steps.dict()
    for step_name in steps:
        cmds[step_name].cmd_func(ctx)
