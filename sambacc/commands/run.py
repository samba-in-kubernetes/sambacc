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

import os

import sambacc.paths as paths

from .cli import commands, Fail
from .initialize import init_container
from .join import join


def _run_container_args(parser):
    parser.add_argument(
        "--no-init",
        action="store_true",
        help=(
            "Do not initialize the container envionment."
            " Only start running the target process."
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
        "target", choices=["smbd", "winbindd"], help="Which process to run"
    )


@commands.command(name="run", arg_func=_run_container_args)
def run_container(cli, config):
    """Run a specified server process."""
    if not getattr(cli, "no_init", False):
        init_container(cli, config)
    else:
        paths.ensure_samba_dirs()
    if cli.target == "smbd":
        # execute smbd process
        cmd = [
            "/usr/sbin/smbd",
            "--foreground",
            "--log-stdout",
            "--no-process-group",
        ]
        os.execvp(cmd[0], cmd)
    elif cli.target == "winbindd":
        if getattr(cli, "insecure_auto_join", False):
            join(cli, config)
        # execute winbind process
        cmd = [
            "/usr/sbin/winbindd",
            "--foreground",
            "--stdout",
            "--no-process-group",
        ]
        os.execvp(cmd[0], cmd)
    else:
        raise Fail(f"invalid target process: {cli.target}")
