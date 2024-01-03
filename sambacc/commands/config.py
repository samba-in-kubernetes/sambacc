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

import argparse
import functools
import logging
import subprocess
import sys
import typing

from sambacc import config
from sambacc import samba_cmds
from sambacc.simple_waiter import watch
import sambacc.netcmd_loader as nc
import sambacc.paths as paths

from .cli import (
    Context,
    best_leader_locator,
    best_waiter,
    commands,
    perms_handler,
    setup_steps,
)

_logger = logging.getLogger(__name__)


@commands.command(name="print-config")
def print_config(ctx: Context) -> None:
    """Display the samba configuration sourced from the sambacc config
    in the format of smb.conf.
    """
    nc.template_config(sys.stdout, ctx.instance_config)


@commands.command(name="import")
@setup_steps.command(name="config")
def import_config(ctx: Context) -> None:
    """Import configuration parameters from the sambacc config to
    samba's registry config.
    """
    # there are some expectations about what dirs exist and perms
    paths.ensure_samba_dirs()

    loader = nc.NetCmdLoader()
    loader.import_config(ctx.instance_config)


def _update_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--watch",
        action="store_true",
        help="If set, watch the source for changes and update config.",
    )


def _read_config(ctx: Context) -> config.InstanceConfig:
    cfgs = ctx.cli.config or []
    return config.read_config_files(
        cfgs,
        require_validation=ctx.require_validation,
        opener=ctx.opener,
    ).get(ctx.cli.identity)


def _update_config(
    current: config.InstanceConfig,
    previous: typing.Optional[config.InstanceConfig],
    ensure_paths: bool = True,
    notify_server: bool = True,
) -> typing.Tuple[config.InstanceConfig, bool]:
    """Compare the current and previous instance configurations. If they
    differ, ensure any new paths, update the samba config, and inform any
    running smbds of the new configuration.  Return the current config and a
    boolean indicating if the instance configs differed.
    """
    # has the config changed?
    changed = current != previous
    # ensure share paths exist
    if changed and ensure_paths:
        for share in current.shares():
            path = share.path()
            if not path:
                continue
            _logger.info(f"Ensuring share path: {path}")
            paths.ensure_share_dirs(path)
            _logger.info(f"Updating permissions if needed: {path}")
            perms_handler(share.permissions_config(), path).update()
    # update smb config
    if changed:
        _logger.info("Updating samba configuration")
        loader = nc.NetCmdLoader()
        loader.import_config(current)
    # notify smbd of changes
    if changed and notify_server:
        subprocess.check_call(
            list(samba_cmds.smbcontrol["smbd", "reload-config"])
        )
    return current, changed


def _exec_if_leader(
    ctx: Context,
    cond_func: typing.Callable[..., typing.Tuple[config.InstanceConfig, bool]],
) -> typing.Callable[..., typing.Tuple[config.InstanceConfig, bool]]:
    """Run the cond func only on "nodes" that are the cluster leader."""

    # CTDB status and leader detection is not changeable at runtime.
    # we do not need to account for it changing in the updated config file(s)
    @functools.wraps(cond_func)
    def _call_if_leader(
        current: config.InstanceConfig, previous: config.InstanceConfig
    ) -> typing.Tuple[config.InstanceConfig, bool]:
        with best_leader_locator(ctx.instance_config) as ll:
            if not ll.is_leader():
                _logger.info("skipping config update. node not leader")
                return previous, False
            _logger.info("checking for update. node is leader")
            result = cond_func(current, previous)
        return result

    return _call_if_leader


@commands.command(name="update-config", arg_func=_update_config_args)
def update_config(ctx: Context) -> None:
    _get_config = functools.partial(_read_config, ctx)
    _cmp_func = _update_config

    if ctx.instance_config.with_ctdb:
        _logger.info("enabling ctdb support: will check for leadership")
        _cmp_func = _exec_if_leader(ctx, _cmp_func)

    if ctx.cli.watch:
        _logger.info("will watch configuration source")
        waiter = best_waiter(ctx.cli.config)
        watch(
            waiter,
            ctx.instance_config,
            _get_config,
            _cmp_func,
        )
    else:
        # we pass None as the previous config so that the command is
        # not nearly always a no-op when run from the command line.
        _cmp_func(_get_config(), None)
    return
