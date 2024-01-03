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
import functools
import logging
import typing

from sambacc import container_dns

from .cli import commands, Context, best_waiter, best_leader_locator, Fail

_logger = logging.getLogger(__name__)


def _dns_register_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--watch",
        action="store_true",
        help="If set, watch the source for changes and update DNS.",
    )
    parser.add_argument(
        "--domain",
        default="",
        help="Manually specify parent domain for DNS entries.",
    )
    parser.add_argument(
        "--target",
        default=container_dns.EXTERNAL,
        choices=[container_dns.EXTERNAL, container_dns.INTERNAL],
        help="Register IPs that fulfill the given access target.",
    )
    parser.add_argument("source", help="Path to source JSON file.")


@commands.command(name="dns-register", arg_func=_dns_register_args)
def dns_register(ctx: Context) -> None:
    """Register container & container orchestration IPs with AD DNS."""
    # This command assumes a cooperating JSON state file.
    # This file is expected to be supplied & kept up to date by
    # a container-orchestration specific component.
    iconfig = ctx.instance_config
    domain = ctx.cli.domain or ""
    if not domain:
        try:
            domain = dict(iconfig.global_options())["realm"].lower()
        except KeyError:
            raise Fail("instance not configured with domain (realm)")

    update_func = functools.partial(
        container_dns.parse_and_update,
        target_name=ctx.cli.target,
    )

    if iconfig.with_ctdb:
        _logger.info("enabling ctdb support: will check for leadership")
        update_func = _exec_if_leader(iconfig, update_func)

    if ctx.cli.watch:
        _logger.info("will watch source")
        waiter = best_waiter(ctx.cli.source)
        container_dns.watch(
            domain,
            ctx.cli.source,
            update_func,
            waiter.wait,
            print_func=print,
        )
    else:
        update_func(domain, ctx.cli.source)
    return


def _exec_if_leader(iconfig, update_func):
    def leader_update_func(
        domain: str,
        source: str,
        previous: typing.Optional[container_dns.HostState] = None,
    ) -> typing.Tuple[typing.Optional[container_dns.HostState], bool]:
        with best_leader_locator(iconfig) as ll:
            if not ll.is_leader():
                _logger.info("skipping dns update. node not leader")
                return previous, False
            _logger.info("checking for update. node is leader")
            result = update_func(domain, source, previous)
        return result

    return leader_update_func
