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

import typing

from . import addc
from . import skips
from .cli import Fail
from .main import (
    CommandContext,
    enable_logging,
    env_to_cli,
    global_args,
    pre_action,
)


default_cfunc = addc.summary


def main(args: typing.Optional[typing.Sequence[str]] = None) -> None:
    cli = addc.dccommands.assemble(arg_func=global_args).parse_args(args)
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
    cfunc = getattr(cli, "cfunc", default_cfunc)
    cfunc(CommandContext(cli))
    return


if __name__ == "__main__":
    main()
