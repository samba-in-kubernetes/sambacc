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
import dataclasses
import functools
import logging
import os
import pathlib
import signal
import subprocess
import sys
import typing


from sambacc import config
from sambacc import samba_cmds
from sambacc.simple_waiter import watch
from sambacc.typelets import Self
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
from .users import sync_sys_users, sync_passdb_users

_logger = logging.getLogger(__name__)


def _log_diff(desc: str, v1: typing.Any, v2: typing.Any) -> None:
    _logger.debug("config objects differ: %s: %r | %r", desc, v1, v2)


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
    parser.add_argument(
        "--signal-pids-dir",
        help=(
            "Directory storing pid files."
            " PIDs saved in files will be sent SIGHUP on config change."
        ),
    )


def _read_config(ctx: Context) -> config.InstanceConfig:
    cfgs = ctx.cli.config or []
    return config.read_config_files(
        cfgs,
        require_validation=ctx.require_validation,
        opener=ctx.opener,
    ).get(ctx.cli.identity)


def _readpid(path: pathlib.Path) -> int:
    try:
        return int(path.read_text())
    except Exception as err:
        _logger.warning("Unable to read pid file %r: %s", path, err)
        return -1


@dataclasses.dataclass(frozen=True)
class ChangeContext:
    current: config.InstanceConfig
    previous: typing.Optional[config.InstanceConfig] = None
    differences: typing.Optional[set[config.DifferenceFlag]] = None
    applied: int = 0
    retry: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.differences)

    @property
    def updated(self) -> bool:
        return bool(self.applied)

    def set_retry(self) -> Self:
        return dataclasses.replace(self, retry=True)

    def _all_differences(self) -> set[config.DifferenceFlag]:
        return set() if self.differences is None else self.differences

    def match(
        self,
        flags: typing.Union[
            config.DifferenceFlag, typing.Iterable[config.DifferenceFlag]
        ],
        *,
        wildcard_type_diff: bool = True,
    ) -> bool:
        """Return true if any of the flags specified are in the differences
        set. If wildcard_type_diff is true, it treats a type mismatch (e.g.
        previous is None) as a flag match.
        """
        adiff = self._all_differences()
        if wildcard_type_diff and config.DifferenceFlag.TYPE in adiff:
            return True
        if isinstance(flags, config.DifferenceFlag):
            flags = [flags]
        return any(f in adiff for f in flags)

    def diff(self) -> Self:
        # cached differences
        if self.differences is not None:
            return self
        # no differences set yet, get fresh
        differences = self.current.compare(self.previous, log_diff=_log_diff)
        _logger.debug("config differences found: %r", differences)
        return dataclasses.replace(self, differences=differences)

    def set_applied(self) -> Self:
        return dataclasses.replace(self, applied=self.applied + 1)

    def shares_by_origin(
        self, origin: config.ShareOrigin
    ) -> list[config.ShareConfig]:
        return [s for s in self.current.shares() if s.meta().origin is origin]


ChangeCheck = typing.Callable[[ChangeContext], ChangeContext]


def _share_paths(
    origin: config.ShareOrigin, chctx: ChangeContext
) -> ChangeContext:
    """Iterate over shares matching the given origin type, ensuring the paths
    and permissions are set up.
    Shares are separated by origin in order to only run this function on
    the appropriate node(s).
    For example: Shares in the local origin can, and should, be set up on all
    nodes in a CTDB cluster while shares in the shared origin should only be
    set up once (by the leader).
    """
    if not chctx.match(config.DifferenceFlag.SHARES):
        return chctx
    for share in chctx.shares_by_origin(origin):
        path = share.path()
        if not path:
            continue
        _logger.info(f"Ensuring share path: {path}")
        paths.ensure_share_dirs(path)
        _logger.info(f"Updating permissions if needed: {path}")
        perms_handler(share.permissions_config(), path).update()
    return chctx.set_applied()


def _samba_config(chctx: ChangeContext) -> ChangeContext:
    if not chctx.changed:
        return chctx
    _logger.info("Updating samba configuration")
    loader = nc.NetCmdLoader()
    loader.import_config(chctx.current)
    try:
        subprocess.check_call(
            list(samba_cmds.smbcontrol["smbd", "reload-config"])
        )
    except subprocess.CalledProcessError as err:
        # smbd may not be up yet (or restarting) and thus not
        # reachable via smbcontrol. This is expected to resolve itself
        # once smbd finishes starting, so don't let it crash the
        # config watch loop.
        _logger.warning(
            "smbcontrol could not notify smbd of the updated"
            " configuration (exit status %s); smbd may still be"
            " starting up and will pick up the change once it is"
            " running: %s",
            err.returncode,
            err,
        )
    return chctx.set_applied()


def _ctr_users_groups(ctx: Context, chctx: ChangeContext) -> ChangeContext:
    """Update host (container) defined users and groups (passwd file) if the
    users/groups have changed.
    """
    if not chctx.match(config.DifferenceFlag.USERS_GROUPS):
        return chctx

    # update users and groups if they changed
    _logger.info("Updating users and groups")
    sync_sys_users(
        chctx.current,
        ctx.cli.passwd_location,
        ctx.cli.group_location,
    )
    return chctx.set_applied()


def _sync_passdb(ctx: Context, chctx: ChangeContext) -> ChangeContext:
    """Update samba's passdb if the users/groups have changed."""
    if not chctx.match(config.DifferenceFlag.USERS_GROUPS):
        return chctx

    # update users and groups if they changed
    _logger.info("Updating samba passdb")
    sync_passdb_users(chctx.current)
    return chctx.set_applied()


def _signal_pids_dir(pids_dir: str, chctx: ChangeContext) -> ChangeContext:
    if not chctx.changed:
        return chctx

    # something changed, send signal to pids found in pid files in dir
    try:
        _pids = [
            _readpid(p)
            for p in pathlib.Path(pids_dir).iterdir()
            if p.name.endswith(".pid")
        ]
    except FileNotFoundError:
        _logger.warning("pids dir not found: %r; skipping pids", pids_dir)
        return chctx

    pids = [pid for pid in _pids if pid > 0]  # filter out errors
    if pids != _pids:
        _logger.warning("Some pid files failed to be read successfully")
    # signal other processes
    for pid in pids:
        try:
            _logger.debug("Sending SIGHUP to %d", pid)
            os.kill(pid, signal.SIGHUP)
        except OSError as err:
            _logger.warning("Failed to SIGHUP %d: %s", pid, err)
    return chctx.set_applied()


def _when_leader(cb: ChangeCheck, chctx: ChangeContext) -> ChangeContext:
    # NOTE: it's important to maintain leader status while running the callback
    # thus the context manager.
    # CTDB enablement and the need for leader detection should not change
    # while the process is running. Thus, _when_leader can wrap all future uses
    # of a change check.
    cbname = getattr(cb, "__name__", "")
    if not cbname and hasattr(cb, "func"):
        cbname = getattr(cb.func, "__name__", f"?{cb}")
    with best_leader_locator(chctx.current) as ll:
        if not ll.is_leader():
            _logger.info("skipping %s. node not leader", cbname)
            return chctx.set_retry()
        _logger.info("executing %s. node is leader", cbname)
        return cb(chctx)
    return chctx


class Trigger:
    def __init__(self) -> None:
        self._actions: list[tuple[str, ChangeCheck]] = []

    def add(self, name: str, fn: ChangeCheck) -> None:
        self._actions.append((name, fn))

    def apply(self, chctx: ChangeContext) -> ChangeContext:
        for name, cb in self._actions:
            _logger.debug("Config change callback: %r", name)
            chctx = cb(chctx.diff())
            _logger.debug(
                "Callback: %r: changed: %r, applied: %r",
                name,
                chctx.changed,
                chctx.applied,
            )
        return chctx

    def __call__(
        self,
        current: config.InstanceConfig,
        previous: typing.Optional[config.InstanceConfig],
    ) -> tuple[typing.Optional[config.InstanceConfig], bool]:
        rctx = self.apply(ChangeContext(current=current, previous=previous))
        if rctx.retry:
            return None, False
        return current, rctx.updated


@commands.command(name="update-config", arg_func=_update_config_args)
def update_config(ctx: Context) -> None:
    _get_config = functools.partial(_read_config, ctx)
    cb_share_paths_local = functools.partial(
        _share_paths, config.ShareOrigin.LOCAL
    )
    cb_share_paths_shared = functools.partial(
        _share_paths, config.ShareOrigin.SHARED
    )
    cb_samba_config = _samba_config
    cb_ctr_users_groups = functools.partial(_ctr_users_groups, ctx)
    cb_passdb = functools.partial(_sync_passdb, ctx)
    trigger = Trigger()

    if ctx.instance_config.with_ctdb:
        _logger.info("enabling ctdb support: will check for leadership")
        cb_share_paths_shared = functools.partial(
            _when_leader, cb_share_paths_shared
        )
        cb_passdb = functools.partial(_when_leader, cb_passdb)
        cb_samba_config = functools.partial(_when_leader, cb_samba_config)
    trigger.add("paths_shared", cb_share_paths_shared)
    trigger.add("paths_local", cb_share_paths_local)
    trigger.add("users_groups", cb_ctr_users_groups)
    trigger.add("sync_passdb", cb_passdb)
    trigger.add("samba", cb_samba_config)
    if pids_dir := ctx.cli.signal_pids_dir:
        trigger.add("pids", functools.partial(_signal_pids_dir, pids_dir))

    if ctx.cli.watch:
        _logger.info("will watch configuration source")
        waiter = best_waiter(ctx.cli.config)
        watch(
            waiter,
            None,
            _get_config,
            trigger,
        )
    else:
        trigger.apply(ChangeContext(current=_get_config()))
    return
