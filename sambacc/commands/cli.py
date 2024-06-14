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
import logging
import typing

from sambacc import config
from sambacc import leader
from sambacc import opener
from sambacc import permissions
from sambacc import simple_waiter

_INOTIFY_OK = True
try:
    from sambacc import inotify_waiter as iw
except ImportError:
    _INOTIFY_OK = False

_logger = logging.getLogger(__name__)


class Fail(ValueError):
    pass


class Parser(typing.Protocol):
    """Minimal protocol for wrapping argument parser or similar."""

    def set_defaults(self, **kwargs: typing.Any) -> None:
        """Set a default value for an argument parser."""
        ...  # pragma: no cover

    def add_argument(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> typing.Any:
        """Add an argument to be parsed."""
        ...  # pragma: no cover


Command = namedtuple("Command", "name cmd_func arg_func cmd_help")


def toggle_option(parser: Parser, arg: str, dest: str, helpfmt: str) -> Parser:
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


def add_command(subparsers: typing.Any, cmd: Command) -> None:
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

    def assemble(
        self, arg_func: typing.Optional[typing.Callable] = None
    ) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        if arg_func is not None:
            arg_func(parser)
        subparsers = parser.add_subparsers()
        for cmd in self._commands:
            add_command(subparsers, cmd)
        return parser

    def dict(self) -> dict[str, Command]:
        """Return a dict mapping command names to Command object."""
        return {c.name: c for c in self._commands}


class Context(typing.Protocol):
    """Protocol type for CLI Context.
    Used to share simple, common state, derived from the CLI, across individual
    command functions.
    """

    # The expects_ctdb attribute indicates that the command can, and should,
    # make use of ctdb whenever ctdb is enabled in the configuration.
    expects_ctdb: bool

    @property
    def cli(self) -> argparse.Namespace:
        """Return a parsed command line namespace object."""
        ...  # pragma: no cover

    @property
    def instance_config(self) -> config.InstanceConfig:
        """Return an instance config based on cli params and env."""
        ...  # pragma: no cover

    @property
    def require_validation(self) -> typing.Optional[bool]:
        """Return true if configuration needs validation."""
        ...  # pragma: no cover

    @property
    def opener(self) -> opener.Opener:
        """Return an appropriate opener object for this instance."""
        ...  # pragma: no cover


def best_waiter(
    filename: typing.Optional[str] = None,
    max_timeout: typing.Optional[int] = None,
) -> simple_waiter.Waiter:
    """Fetch the best waiter type for our sambacc command."""
    if filename and _INOTIFY_OK:
        _logger.info("enabling inotify support")
        return iw.INotify(
            filename, print_func=_logger.info, timeout=max_timeout
        )
    # should max_timeout change Sleeper too? probably.
    return simple_waiter.Sleeper()


def best_leader_locator(
    iconfig: config.InstanceConfig,
) -> leader.LeaderLocator:
    """Fetch the best leader locator for our sambacc command.
    This only makes sense to be used in a clustered scenario.
    """
    from sambacc import ctdb

    return ctdb.CLILeaderLocator()


def perms_handler(
    config: config.PermissionsConfig,
    path: str,
) -> permissions.PermissionsHandler:
    """Fetch and instantiate the appropriate permissions handler for the given
    configuration.
    """
    if config.method == "none":
        _logger.info("Using no-op permissions handler")
        return permissions.NoopPermsHandler(
            path, config.status_xattr, options=config.options
        )
    if config.method == "initialize-share-perms":
        _logger.info("Using initializing posix permissions handler")
        return permissions.InitPosixPermsHandler(
            path, config.status_xattr, options=config.options
        )
    if config.method == "always-share-perms":
        _logger.info("Using always-setting posix permissions handler")
        return permissions.AlwaysPosixPermsHandler(
            path, config.status_xattr, options=config.options
        )
    # fall back to init perms handler
    _logger.info("Using initializing posix permissions handler")
    return permissions.InitPosixPermsHandler(
        path, config.status_xattr, options=config.options
    )


commands = CommandBuilder()
setup_steps = CommandBuilder()
