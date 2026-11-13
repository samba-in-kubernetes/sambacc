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

import contextlib
import logging
import os
import signal
import time
import typing

from sambacc import samba_cmds
import sambacc.paths as paths

from .cli import commands, Context, Fail
from .initialize import init_container, setup_step_names
from .join import join

_logger = logging.getLogger(__name__)

INIT_ALL = "init-all"
SMBD = "smbd"
WINBINDD = "winbindd"
CTDBD = "ctdbd"
CONFIGWATCH = "configwatch"
TARGETS = [SMBD, WINBINDD, CTDBD, CONFIGWATCH]


class WaitForCTDBCondition:
    def met(self, ctx: Context) -> bool:
        target = getattr(ctx.cli, "target", None)
        if target == CTDBD:
            raise Fail(f"Can not start and wait for {CTDBD}")
        _logger.debug("Condition required: ctdb pnn available")
        import sambacc.ctdb

        pnn = sambacc.ctdb.current_pnn()
        ok = pnn is not None
        _logger.debug(
            "Condition %s: ctdb pnn available: %s",
            "met" if ok else "not met",
            pnn,
        )
        return ok


_wait_for_conditions = {"ctdb": WaitForCTDBCondition}


def _run_container_args(parser):
    parser.add_argument(
        "--no-init",
        action="store_true",
        help=(
            "(DEPRECATED - see --setup) Do not initialize the container"
            " envionment. Only start running the target process."
        ),
    )
    _setup_choices = [INIT_ALL] + list(setup_step_names())
    parser.add_argument(
        "--setup",
        action="append",
        choices=_setup_choices,
        help=(
            "Specify one or more setup step names to preconfigure the"
            " container environment before the server process is started."
            " The special 'init-all' name will perform all known setup steps."
            " Additional steps may be appended to this list via the"
            " SAMBACC_EXTRA_SETUP env variable."
            " When using SAMBACC_EXTRA_SETUP separate step names with commas."
        ),
    )
    _wait_for_choices = _wait_for_conditions.keys()
    parser.add_argument(
        "--wait-for",
        action="append",
        choices=_wait_for_choices,
        help=(
            "Specify a condition to wait for prior to starting the server"
            " process. Available conditions: `ctdb` - wait for ctdb"
            " to run and provide a pnn."
        ),
    )
    parser.add_argument(
        "--insecure-auto-join",
        action="store_true",
        help=(
            "Perform an inscure domain join prior to starting a service."
            " Based on env vars JOIN_USERNAME and INSECURE_JOIN_PASSWORD."
        ),
    )
    # XXX: HACK - for embedded configwatch (starts with --config-watch- for
    # pseudo namespacing)
    parser.add_argument(
        "--config-watch-signal-pids-dir",
        dest="signal_pids_dir",
        help=(
            "Directory storing pid files."
            " PIDs saved in files will be sent SIGHUP on config change."
        ),
    )
    parser.add_argument(
        "target",
        choices=TARGETS,
        help="Which process to run",
    )


_COND_TIMEOUT = 5 * 60


@contextlib.contextmanager
def _timeout(timeout: int) -> typing.Iterator[None]:
    def _handler(sig: int, frame: typing.Any) -> None:
        raise RuntimeError("timed out waiting for conditions")

    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, signal.SIG_DFL)


def _extra_setup_steps() -> list[str]:
    """Return setup steps from the comma separated SAMBACC_EXTRA_SETUP."""
    value = os.environ.get("SAMBACC_EXTRA_SETUP", "")
    steps = [s.strip() for s in value.split(",") if s.strip()]
    valid = list(setup_step_names())
    for step in steps:
        if step not in valid:
            raise Fail(f"invalid step in SAMBACC_EXTRA_SETUP: {step}")
    return steps


def _perform_setup(ctx: Context) -> None:
    extra_steps = _extra_setup_steps()
    # running servers expect to make use of ctdb whenever it is configured
    ctx.expects_ctdb = True
    if ctx.cli.no_init:
        # TODO: drop this along with --no-init and move to a opt-in
        # rather than opt-out form of pre-run setup
        return
    steps: list[str] | None = None
    if ctx.cli.setup:
        steps = list(ctx.cli.setup)
        steps = None if INIT_ALL in steps else steps
    init_container(ctx, steps=steps, extra_steps=extra_steps)


@commands.command(name="run", arg_func=_run_container_args)
def run_container(ctx: Context) -> None:
    """Run a specified server process."""
    if ctx.cli.no_init and ctx.cli.setup:
        raise Fail("can not specify both --no-init and --setup")

    if ctx.cli.wait_for:
        with _timeout(_COND_TIMEOUT):
            conditions = [_wait_for_conditions[n]() for n in ctx.cli.wait_for]
            while not all(c.met(ctx) for c in conditions):
                time.sleep(1)

    _perform_setup(ctx)

    paths.ensure_samba_dirs()
    if ctx.cli.target == "smbd":
        # execute smbd process
        samba_cmds.execute(samba_cmds.smbd_foreground())
    elif ctx.cli.target == "winbindd":
        if getattr(ctx.cli, "insecure_auto_join", False):
            join(ctx)
        # execute winbind process
        samba_cmds.execute(samba_cmds.winbindd_foreground())
    elif ctx.cli.target == "ctdbd":
        samba_cmds.execute(samba_cmds.ctdbd_foreground)
    elif ctx.cli.target == CONFIGWATCH:
        _wrap_configwatch(ctx)
    else:
        raise Fail(f"invalid target process: {ctx.cli.target}")


def _wrap_configwatch(ctx: Context) -> None:
    """Start configwatch (update-config --watch) via the run command instead of
    the normal path, allowing configwatch to "steal" the setup capabilties of
    the run subcommand without needing to do a huge refactoring of the command
    handling/--setup args.
    """
    import sambacc.commands.config

    ctx.cli.watch = True
    sambacc.commands.config.update_config(ctx)
