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

import sys
import typing

import sambacc.join as joinutil

from .cli import (
    Context,
    Fail,
    Parser,
    best_waiter,
    commands,
    toggle_option,
)


def _print_join_error(err: typing.Any) -> None:
    print(f"ERROR: {err}", file=sys.stderr)
    for suberr in getattr(err, "errors", []):
        print(f"  - {suberr}", file=sys.stderr)


def _add_join_sources(joiner: joinutil.Joiner, cli: typing.Any) -> None:
    if cli.insecure or getattr(cli, "insecure_auto_join", False):
        upass = joinutil.UserPass(cli.username, cli.password)
        joiner.add_source(joinutil.JoinBy.PASSWORD, upass)
    if cli.files:
        for path in cli.join_files or []:
            joiner.add_source(joinutil.JoinBy.FILE, path)
    if cli.interactive:
        upass = joinutil.UserPass(cli.username)
        joiner.add_source(joinutil.JoinBy.INTERACTIVE, upass)


def _join_args(parser: Parser) -> None:
    parser.set_defaults(insecure=False, files=True, interactive=True)
    toggle_option(
        parser,
        arg="--insecure",
        dest="insecure",
        helpfmt="{} taking user/password from CLI or environment.",
    )
    toggle_option(
        parser,
        arg="--files",
        dest="files",
        helpfmt="{} reading user/password from JSON files.",
    )
    toggle_option(
        parser,
        arg="--interactive",
        dest="interactive",
        helpfmt="{} interactive password prompt.",
    )
    parser.add_argument(
        "--join-file",
        "-j",
        dest="join_files",
        action="append",
        help="Path to file with user/password in JSON format.",
    )


@commands.command(name="join", arg_func=_join_args)
def join(ctx: Context) -> None:
    """Perform a domain join. The supported sources for join
    can be provided by supplying command line arguments.
    This includes an *insecure* mode that sources the password
    from the CLI or environment. Use this only on
    testing/non-production purposes.
    """
    # maybe in the future we'll have more secure methods
    joiner = joinutil.Joiner(ctx.cli.join_marker, opener=ctx.opener)
    _add_join_sources(joiner, ctx.cli)
    try:
        joiner.join()
    except joinutil.JoinError as err:
        _print_join_error(err)
        raise Fail("failed to join to a domain")


def _must_join_args(parser: Parser) -> None:
    parser.set_defaults(insecure=False, files=True, wait=True)
    toggle_option(
        parser,
        arg="--insecure",
        dest="insecure",
        helpfmt="{} taking user/password from CLI or environment.",
    )
    toggle_option(
        parser,
        arg="--files",
        dest="files",
        helpfmt="{} reading user/password from JSON files.",
    )
    toggle_option(
        parser,
        arg="--wait",
        dest="wait",
        helpfmt="{} waiting until a join is done.",
    )
    parser.add_argument(
        "--join-file",
        "-j",
        dest="join_files",
        action="append",
        help="Path to file with user/password in JSON format.",
    )


@commands.command(name="must-join", arg_func=_must_join_args)
def must_join(ctx: Context) -> None:
    """If possible, perform an unattended domain join. Otherwise,
    exit or block until a join has been perfmed by another process.
    """
    joiner = joinutil.Joiner(ctx.cli.join_marker, opener=ctx.opener)
    if joiner.did_join():
        print("already joined")
        return
    # Interactive join is not allowed on must-join
    setattr(ctx.cli, "interactive", False)
    _add_join_sources(joiner, ctx.cli)
    if ctx.cli.wait:
        waiter = best_waiter(ctx.cli.join_marker, max_timeout=120)
        joinutil.join_when_possible(
            joiner, waiter, error_handler=_print_join_error
        )
    else:
        try:
            joiner.join()
        except joinutil.JoinError as err:
            _print_join_error(err)
            raise Fail(
                "failed to join to a domain - waiting for join is disabled"
            )
