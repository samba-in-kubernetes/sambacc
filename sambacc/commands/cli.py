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
import importlib
import inspect
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

    def add_argument(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> typing.Any:
        """Add an argument to be parsed."""


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


def ceph_id(
    value: typing.Union[str, dict[str, typing.Any]]
) -> dict[str, typing.Any]:
    """Parse a string value into a dict containing ceph id values.
    The input should contain name= or rados_id= to identify the kind
    of name being provided. As a shortcut a bare name can be provided
    and the code will guess at the kind.
    """
    if not isinstance(value, str):
        return value
    if value == "?":
        # A hack to avoid putting tons of ceph specific info in the normal
        # help output. There's probably a better way to do this but it
        # gets the job done for now.
        raise argparse.ArgumentTypeError(
            "requested help:"
            " Specify names in the form"
            " --ceph-id=[key=value][,key=value][,...]."
            ' Valid keys include "name" to set the exact name and "rados_id"'
            ' to specify a name that lacks the "client." prefix (that will'
            "automatically get added)."
            " Alternatively, specify just the name to allow the system to"
            " guess if the name is prefixed already or not."
        )
    result: dict[str, typing.Any] = {}
    # complex mode
    if "=" in value:
        for part in value.split(","):
            if "=" not in part:
                raise argparse.ArgumentTypeError(
                    f"unexpected value for ceph-id: {value!r}"
                )
            key, val = part.split("=", 1)
            if key == "name":
                result["client_name"] = val
                result["full_name"] = True
            elif key == "rados_id":
                result["client_name"] = val
                result["full_name"] = False
            else:
                b = f"unexpected key {key!r} in value for ceph-id: {value!r}"
                raise argparse.ArgumentTypeError(b)
    else:
        # this shorthand is meant mainly for lazy humans (me) when running test
        # images manually. The key-value form above is meant for automation.
        result["client_name"] = value
        # assume that if the name starts with client. it's the full name and
        # avoid having the ceph library double up an create client.client.x.
        result["full_name"] = value.startswith("client.")
    return result


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

    def include(
        self, modname: str, *, package: str = "", check: bool = True
    ) -> None:
        """Import a python module to add commands to this command builder.
        If check is true and no new commands are added by the import, raise an
        error.
        """
        if modname.startswith(".") and not package:
            package = "sambacc.commands"
        mod = importlib.import_module(modname, package=package)
        if not check:
            return
        loaded_fns = {c.cmd_func for c in self._commands}
        mod_fns = {fn for _, fn in inspect.getmembers(mod, inspect.isfunction)}
        if not mod_fns.intersection(loaded_fns):
            raise Fail(f"import from {modname} did not add any new commands")

    def include_multiple(
        self, modnames: typing.Iterable[str], *, package: str = ""
    ) -> None:
        """Run the include function on multiple module names."""
        for modname in modnames:
            self.include(modname, package=package)


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

    @property
    def instance_config(self) -> config.InstanceConfig:
        """Return an instance config based on cli params and env."""

    @property
    def require_validation(self) -> typing.Optional[bool]:
        """Return true if configuration needs validation."""

    @property
    def opener(self) -> opener.Opener:
        """Return an appropriate opener object for this instance."""


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
