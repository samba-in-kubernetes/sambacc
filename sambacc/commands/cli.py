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

from collections import namedtuple
import argparse
import typing

from sambacc import config
from sambacc import simple_waiter

_INOTIFY_OK = True
try:
    from sambacc import inotify_waiter as iw
except ImportError:
    _INOTIFY_OK = False


class Fail(ValueError):
    pass


Command = namedtuple("Command", "name cmd_func arg_func cmd_help")


def toggle_option(
    parser: argparse.ArgumentParser, arg: str, dest: str, helpfmt: str
) -> argparse.ArgumentParser:
    parser.add_argument(
        arg,
        action="store_true",
        dest=dest,
        help=helpfmt.format("Enable"),
    )
    negarg = arg.replace("--", "--no-")
    parser.add_argument(
        negarg,
        action="store_false",
        dest=dest,
        help=helpfmt.format("Disable"),
    )
    return parser


def get_help(cmd: Command) -> str:
    if cmd.cmd_help is not None:
        return cmd.cmd_help
    if cmd.cmd_func.__doc__:
        return cmd.cmd_func.__doc__
    return ""


def add_command(subparsers, cmd) -> None:
    subparser = subparsers.add_parser(cmd.name, help=get_help(cmd))
    subparser.set_defaults(cfunc=cmd.cmd_func)
    if cmd.arg_func is not None:
        cmd.arg_func(subparser)


class CommandBuilder:
    def __init__(self):
        self._commands = []
        self._names = set()

    def command(self, name, arg_func=None, cmd_help=None):
        if name in self._names:
            raise ValueError(f"{name} already in use")
        self._names.add(name)

        def _wrapper(f):
            self._commands.append(
                Command(
                    name=name, cmd_func=f, arg_func=arg_func, cmd_help=cmd_help
                )
            )
            return f

        return _wrapper

    def assemble(self, arg_func=None) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        if arg_func is not None:
            arg_func(parser)
        subparsers = parser.add_subparsers()
        for cmd in self._commands:
            add_command(subparsers, cmd)
        return parser


class Context(typing.Protocol):
    """Protocol type for CLI Context.
    Used to share simple, common state, derived from the CLI, across individual
    command functions.
    """
    @property
    def cli(self) -> argparse.Namespace:
        ...

    @property
    def instance_config(self) -> config.InstanceConfig:
        ...


def best_waiter(
    filename: typing.Optional[str] = None,
    max_timeout: typing.Optional[int] = None,
) -> simple_waiter.Waiter:
    """Fetch the best waiter type for our sambacc command."""
    if filename and _INOTIFY_OK:
        print("enabling inotify support")
        return iw.INotify(filename, print_func=print, timeout=max_timeout)
    # should max_timeout change Sleeper too? probably.
    return simple_waiter.Sleeper()


commands = CommandBuilder()
