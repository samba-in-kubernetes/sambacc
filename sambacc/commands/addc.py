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

import logging
import os
import shutil

from sambacc import addc
from sambacc import samba_cmds

from .cli import CommandBuilder, Context

_logger = logging.getLogger(__name__)

_populated: str = "/var/lib/samba/POPULATED"
_provisioned: str = "/etc/samba/smb.conf"

dccommands = CommandBuilder()


@dccommands.command(name="summary")
def summary(ctx: Context) -> None:
    print("Hello", ctx)


_setup_choices = ["init-all", "provision", "populate"]


def _dosetup(ctx: Context, step_name: str) -> bool:
    setup = ctx.cli.setup or []
    return ("init-all" in setup) or (step_name in setup)


def _run_container_args(parser):
    parser.add_argument(
        "--setup",
        action="append",
        choices=_setup_choices,
        help=(
            "Specify one or more setup step names to preconfigure the"
            " container environment before the server process is started."
            " The special 'init-all' name will perform all known setup steps."
        ),
    )


def _prep_provision(ctx: Context) -> None:
    if os.path.exists(_provisioned):
        _logger.info("Domain already provisioned")
        return
    _logger.info("Provisioning domain")

    addc.provision(
        realm="DOMAIN1.SINK.TEST",
        domain="DOMAIN1",
        dcname="dc1",
        admin_password="Passw0rd",
    )


def _prep_populate(ctx: Context) -> None:
    if os.path.exists(_populated):
        _logger.info("populated marker exists")
        return
    _logger.info("Populating domain with default entries")

    addc.create_group("supervisors")
    addc.create_group("employees")
    addc.create_group("characters")
    addc.create_group("bulk")

    pw = "1115Rose."
    addc.create_user(name="johnm", password=pw, surname="John", given_name="M")
    addc.create_user(
        name="ckent", password=pw, surname="Clark", given_name="Kent"
    )
    addc.create_user(
        name="bwayne", password=pw, surname="Bruce", given_name="Wayne"
    )
    addc.create_user(
        name="bbanner", password=pw, surname="Bruce", given_name="Banner"
    )
    addc.create_user(
        name="pparker", password=pw, surname="Peter", given_name="Parker"
    )

    addc.add_group_members(group_name="supervisors", members=["johnm"])
    addc.add_group_members(
        group_name="employees",
        members=["johnm", "ckent", "bwayne", "pparker", "bbanner"],
    )
    addc.add_group_members(
        group_name="characters",
        members=["ckent", "bwayne", "pparker", "bbanner"],
    )

    for i in range(42):
        uname = f"user{i}"
        addc.create_user(
            name=uname, password=pw, surname="Hue-Sir", given_name=f"George{i}"
        )
        addc.add_group_members(group_name="bulk", members=[uname])

    # "touch" the populated marker
    with open(_populated, "w"):
        pass


def _prep_krb5_conf(ctx: Context) -> None:
    shutil.copy("/var/lib/samba/private/krb5.conf", "/etc/krb5.conf")


@dccommands.command(name="run", arg_func=_run_container_args)
def run(ctx: Context) -> None:
    _logger.info("Running AD DC container")
    if _dosetup(ctx, "provision"):
        _prep_provision(ctx)
    if _dosetup(ctx, "populate"):
        _prep_populate(ctx)

    _prep_krb5_conf(ctx)
    _logger.info("Starting samba server")
    samba_cmds.execute(samba_cmds.samba_dc_foreground())
