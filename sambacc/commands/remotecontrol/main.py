#
# sambacc: a samba container configuration tool
# Copyright (C) 2025  John Mulligan
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

import sys
import typing


from .. import skips
from ..cli import Context, Fail, commands
from ..common import (
    CommandContext,
    enable_logging,
    env_to_cli,
    global_args,
    pre_action,
)


def _default(ctx: Context) -> None:
    sys.stdout.write(f"{sys.argv[0]} requires a subcommand, like 'serve'.\n")
    sys.exit(1)


def main(args: typing.Optional[typing.Sequence[str]] = None) -> None:
    pkg = "sambacc.commands.remotecontrol"
    commands.include(".server", package=pkg)

    cli = commands.assemble(arg_func=global_args).parse_args(args)
    env_to_cli(cli)
    enable_logging(cli)
    if not cli.identity:
        raise Fail("missing container identity")

    pre_action(cli)
    ctx = CommandContext(cli)
    skip = skips.test(ctx)
    if skip:
        print(f"Command Skipped: {skip}")
        return
    cfunc = getattr(cli, "cfunc", _default)
    cfunc(ctx)
    return


if __name__ == "__main__":
    main()
