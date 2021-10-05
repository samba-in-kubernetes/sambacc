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

from sambacc import samba_cmds
import sambacc.paths as paths

from .cli import commands, Context, Fail
from .initialize import init_container, setup_step_names
from .join import join


INIT_ALL = "init-all"


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
    parser.add_argument(
        "target",
        choices=["smbd", "winbindd", "ctdbd"],
        help="Which process to run",
    )


@commands.command(name="run", arg_func=_run_container_args)
def run_container(ctx: Context) -> None:
    """Run a specified server process."""
    if ctx.cli.no_init and ctx.cli.setup:
        raise Fail("can not specify both --no-init and --setup")
    # running servers expect to make use of ctdb whenever it is configured
    ctx.expects_ctdb = True
    if not ctx.cli.no_init and not ctx.cli.setup:
        # TODO: drop this along with --no-init and move to a opt-in
        # rather than opt-out form of pre-run setup
        init_container(ctx)
    elif ctx.cli.setup:
        steps = list(ctx.cli.setup)
        init_container(ctx, steps=(None if INIT_ALL in steps else steps))

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
    else:
        raise Fail(f"invalid target process: {ctx.cli.target}")
