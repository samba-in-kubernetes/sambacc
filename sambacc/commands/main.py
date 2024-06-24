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
import json
import logging
import os
import time
import typing

from sambacc import config
from sambacc import opener
from sambacc import rados_opener
from sambacc import samba_cmds
from sambacc import url_opener

from . import check  # noqa: F401
from . import config as config_cmds
from . import ctdb  # noqa: F401
from . import dns  # noqa: F401
from . import initialize  # noqa: F401
from . import join  # noqa: F401
from . import run  # noqa: F401
from . import skips
from . import users  # noqa: F401
from .cli import commands, Fail, Parser

DEFAULT_CONFIG = "/etc/samba/container/config.json"
DEFAULT_JOIN_MARKER = "/var/lib/samba/container-join-marker.json"

default_cfunc = config_cmds.print_config


def global_args(parser: Parser) -> None:
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
        "--skip-if",
        dest="skip_conditions",
        action="append",
        type=skips.parse,
        help=(
            "Skip execution based on a condition. Conditions include"
            " 'file:[!]<path>', 'env:<var>(==|!=)<value>', and 'always:'."
            " (Pass `?` for more details)"
        ),
    )
    parser.add_argument(
        "--skip-if-file",
        action="append",
        dest="skip_conditions",
        type=skips.SkipFile.parse,
        help="(DEPRECATED) Perform no action if the specified path exists.",
    )
    parser.add_argument(
        "--validate-config",
        choices=("auto", "required", "true", "false"),
        help="Perform schema based validation of configuration.",
    )
    parser.add_argument(
        "--ceph-id",
        type=_ceph_id,
        help=(
            "Specify a user/client ID to ceph libraries"
            "(can also be set in the environment by SAMBACC_CEPH_ID."
            " Ignored if Ceph RADOS libraries are not present or unused."
            " Pass `?` for more details)."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug level logging of sambacc.",
    )


def _ceph_id(
    value: typing.Union[str, dict[str, typing.Any]]
) -> dict[str, typing.Any]:
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


def from_env(
    ns: typing.Any,
    var: str,
    ename: str,
    default: typing.Any = None,
    convert_env: typing.Optional[typing.Callable] = None,
    convert_value: typing.Optional[typing.Callable] = str,
) -> None:
    value = getattr(ns, var, None)
    if not value:
        value = os.environ.get(ename, "")
        if convert_env is not None:
            value = convert_env(value)
    if convert_value is not None:
        value = convert_value(value)
    if value:
        setattr(ns, var, value)


def split_entries(value):
    out = []
    if not isinstance(value, str):
        raise ValueError(value)
    if not value:
        return out
    # in order to cleanly allow passing uris as config "paths" we can't
    # simply split on colons. Avoid coming up with a hokey custom scheme
    # and enter "JSON-mode" if the env var starts and ends with brackets
    # hinting it contains a JSON list.
    v = value.rstrip(None)  # permit trailing whitespace (trailing only!)
    if v[0] == "[" and v[-1] == "]":
        for item in json.loads(v):
            if not isinstance(item, str):
                raise ValueError("Variable JSON must be a list of strings")
            out.append(item)
    else:
        # backwards compatibilty mode with `PATH` like syntax
        for part in value.split(":"):
            out.append(part)
    return out


def env_to_cli(cli: typing.Any) -> None:
    from_env(
        cli,
        "config",
        "SAMBACC_CONFIG",
        convert_env=split_entries,
        convert_value=None,
        default=DEFAULT_CONFIG,
    )
    from_env(
        cli,
        "join_files",
        "SAMBACC_JOIN_FILES",
        convert_env=split_entries,
        convert_value=None,
    )
    from_env(cli, "identity", "SAMBA_CONTAINER_ID")
    from_env(cli, "username", "JOIN_USERNAME")
    from_env(cli, "password", "INSECURE_JOIN_PASSWORD")
    from_env(cli, "samba_debug_level", "SAMBA_DEBUG_LEVEL")
    from_env(cli, "validate_config", "SAMBACC_VALIDATE_CONFIG")
    from_env(cli, "ceph_id", "SAMBACC_CEPH_ID", convert_value=_ceph_id)


class CommandContext:
    """CLI Context for standard samba-container commands."""

    def __init__(self, cli_args: argparse.Namespace):
        self._cli = cli_args
        self._iconfig: typing.Optional[config.InstanceConfig] = None
        self.expects_ctdb = False
        self._opener: typing.Optional[opener.Opener] = None

    @property
    def cli(self) -> argparse.Namespace:
        return self._cli

    @property
    def instance_config(self) -> config.InstanceConfig:
        if self._iconfig is None:
            cfgs = self.cli.config or []
            self._iconfig = config.read_config_files(
                cfgs,
                require_validation=self.require_validation,
                opener=self.opener,
            ).get(self.cli.identity)
        return self._iconfig

    @property
    def require_validation(self) -> typing.Optional[bool]:
        if self.cli.validate_config in ("required", "true"):
            return True
        if self.cli.validate_config == "false":
            return False
        return None

    @property
    def opener(self) -> opener.Opener:
        if self._opener is None:
            self._opener = opener.FallbackOpener([url_opener.URLOpener()])
        return self._opener


def pre_action(cli: typing.Any) -> None:
    """Handle debugging/diagnostic related options before the target
    action of the command is performed.
    """
    if cli.debug_delay:
        time.sleep(int(cli.debug_delay))
    if cli.samba_debug_level:
        samba_cmds.set_global_debug(cli.samba_debug_level)
    if cli.samba_command_prefix:
        samba_cmds.set_global_prefix([cli.samba_command_prefix])

    # should there be an option to force {en,dis}able rados?
    # Right now we just always try to enable rados when possible.
    rados_opener.enable_rados(
        url_opener.URLOpener,
        client_name=cli.ceph_id.get("client_name", ""),
        full_name=cli.ceph_id.get("full_name", False),
    )


def enable_logging(cli: typing.Any) -> None:
    level = logging.DEBUG if cli.debug else logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("{asctime}: {levelname}: {message}", style="{")
    )
    handler.setLevel(level)
    logger.addHandler(handler)


def main(args: typing.Optional[typing.Sequence[str]] = None) -> None:
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
    cfunc = getattr(cli, "cfunc", default_cfunc)
    cfunc(ctx)
    return


if __name__ == "__main__":
    main()
