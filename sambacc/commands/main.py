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
import logging
import os
import time
import typing

from sambacc import config
from sambacc import samba_cmds

from . import check  # noqa: F401
from . import config as config_cmds
from . import ctdb  # noqa: F401
from . import dns  # noqa: F401
from . import initialize  # noqa: F401
from . import join  # noqa: F401
from . import run  # noqa: F401
from . import users  # noqa: F401
from .cli import commands, Fail

DEFAULT_CONFIG = "/etc/samba/container/config.json"
DEFAULT_JOIN_MARKER = "/var/lib/samba/container-join-marker.json"

default_cfunc = config_cmds.print_config


def global_args(parser) -> None:
    parser.add_argument(
        "--config",
        action="append",
        help=(
            "Specify source configuration"
            " (can also be set in the environment by SAMBACC_CONFIG)."
        ),
    )
    parser.add_argument(
        "--identity",
        help=(
            "A string identifying the local identity"
            " (can also be set in the environment by SAMBA_CONTAINER_ID)."
        ),
    )
    parser.add_argument(
        "--etc-passwd-path",
        default="/etc/passwd",
        help="Specify a path for the passwd file.",
    )
    parser.add_argument(
        "--etc-group-path",
        default="/etc/group",
        help="Specify a path for the group file.",
    )
    parser.add_argument(
        "--username",
        default="Administrator",
        help="Specify a user name for domain access.",
    )
    parser.add_argument(
        "--password", default="", help="Specify a password for domain access."
    )
    parser.add_argument(
        "--debug-delay",
        type=int,
        help="Delay activity for a specified number of seconds.",
    )
    parser.add_argument(
        "--join-marker",
        default=DEFAULT_JOIN_MARKER,
        help="Path to a file used to indicate a join has been peformed.",
    )
    parser.add_argument(
        "--samba-debug-level",
        choices=[str(v) for v in range(0, 11)],
        help="Specify samba debug level for commands.",
    )
    parser.add_argument(
        "--samba-command-prefix",
        help="Wrap samba commands within a supplied command prefix",
    )
    parser.add_argument(
        "--skip-if-file",
        action="append",
        help=("Perform no action if the specified path exists."),
    )


def from_env(ns, var, ename, default=None, vtype=str) -> None:
    value = getattr(ns, var, None)
    if not value:
        value = os.environ.get(ename, "")
    if vtype is not None:
        value = vtype(value)
    if value:
        setattr(ns, var, value)


def split_paths(value):
    if not value:
        return value
    if not isinstance(value, list):
        value = [value]
    out = []
    for v in value:
        for part in v.split(":"):
            out.append(part)
    return out


def env_to_cli(cli) -> None:
    from_env(
        cli,
        "config",
        "SAMBACC_CONFIG",
        vtype=split_paths,
        default=DEFAULT_CONFIG,
    )
    from_env(
        cli,
        "join_files",
        "SAMBACC_JOIN_FILES",
        vtype=split_paths,
    )
    from_env(cli, "identity", "SAMBA_CONTAINER_ID")
    from_env(cli, "username", "JOIN_USERNAME")
    from_env(cli, "password", "INSECURE_JOIN_PASSWORD")
    from_env(cli, "samba_debug_level", "SAMBA_DEBUG_LEVEL")


class CommandContext:
    """CLI Context for standard samba-container commands."""

    def __init__(self, cli_args: argparse.Namespace):
        self._cli = cli_args
        self._iconfig: typing.Optional[config.InstanceConfig] = None
        self.expects_ctdb = False

    @property
    def cli(self) -> argparse.Namespace:
        return self._cli

    @property
    def instance_config(self) -> config.InstanceConfig:
        if self._iconfig is None:
            cfgs = self.cli.config or []
            self._iconfig = config.read_config_files(cfgs).get(
                self.cli.identity
            )
        return self._iconfig


def pre_action(cli) -> None:
    """Handle debugging/diagnostic related options before the target
    action of the command is performed.
    """
    if cli.debug_delay:
        time.sleep(int(cli.debug_delay))
    if cli.samba_debug_level:
        samba_cmds.set_global_debug(cli.samba_debug_level)
    if cli.samba_command_prefix:
        samba_cmds.set_global_prefix([cli.samba_command_prefix])


def enable_logging(cli) -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("{asctime}: {levelname}: {message}", style="{")
    )
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)


def action_filter(cli) -> typing.Optional[str]:
    for path in cli.skip_if_file or []:
        if os.path.exists(path):
            return f"skip-if-file: {path} exists"
    return None


def main(args=None) -> None:
    cli = commands.assemble(arg_func=global_args).parse_args(args)
    env_to_cli(cli)
    enable_logging(cli)
    if not cli.identity:
        raise Fail("missing container identity")

    pre_action(cli)
    skip = action_filter(cli)
    if skip:
        print(f"Action skipped: {skip}")
        return
    cfunc = getattr(cli, "cfunc", default_cfunc)
    cfunc(CommandContext(cli))
    return


if __name__ == "__main__":
    main()
