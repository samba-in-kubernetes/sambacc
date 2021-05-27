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

from sambacc import container_dns
from sambacc import simple_waiter

from .cli import commands, Fail

_INOTIFY_OK = True
try:
    from sambacc import inotify_waiter as iw
except ImportError:
    _INOTIFY_OK = False


def _waiter(filename=None):
    if filename and _INOTIFY_OK:
        print("enabling inotify support")
        return iw.INotify(filename, print_func=print)
    return simple_waiter.Sleeper()


def _dns_register_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--watch",
        action="store_true",
        help=("If set, watch the source for changes and update DNS."),
    )
    parser.add_argument(
        "--domain",
        default="",
        help=("Manually specify parent domain for DNS entries."),
    )
    parser.add_argument("source", help="Path to source JSON file.")


@commands.command(name="dns-register", arg_func=_dns_register_args)
def dns_register(cli, config) -> None:
    """Register container & container orchestration IPs with AD DNS."""
    # This command assumes a cooperating JSON state file.
    # This file is expected to be supplied & kept up to date by
    # a container-orchestration specific component.
    cfgs = cli.config or []
    iconfig = config.read_config_files(cfgs).get(cli.identity)
    domain = cli.domain or ""
    if not domain:
        try:
            domain = dict(iconfig.global_options())["realm"].lower()
        except KeyError:
            raise Fail("instance not configured with domain (realm)")

    if cli.watch:
        waiter = _waiter(cli.source)
        container_dns.watch(
            domain,
            cli.source,
            container_dns.parse_and_update,
            waiter.wait,
            print_func=print,
        )
    else:
        container_dns.parse_and_update(domain, cli.source)
    return
