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
import typing

from sambacc import addc
from sambacc import samba_cmds
from sambacc import smbconf_api
from sambacc import smbconf_samba

from .cli import best_waiter, CommandBuilder, Context, Fail

try:
    import dns
    import dns.resolver
    import dns.exception

    _DNS = True
except ImportError:
    _DNS = False


_logger = logging.getLogger(__name__)

_populated: str = "/var/lib/samba/POPULATED"
_provisioned: str = "/etc/samba/smb.conf"

dccommands = CommandBuilder()


@dccommands.command(name="summary")
def summary(ctx: Context) -> None:
    print("Hello", ctx)


_setup_choices = ["init-all", "provision", "populate", "wait-domain", "join"]


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
    parser.add_argument(
        "--name",
        help="Specify a custom name for the dc, overriding the config file.",
    )


def _prep_provision(ctx: Context) -> None:
    if os.path.exists(_provisioned):
        _logger.info("Domain already provisioned")
        return
    domconfig = ctx.instance_config.domain()
    _logger.info(f"Provisioning domain: {domconfig.realm}")

    dcname = ctx.cli.name or domconfig.dcname
    prov_opts = list(ctx.instance_config.global_options())
    explicit_ifaces = "interfaces" in dict(prov_opts)
    if domconfig.interface_config.configured and not explicit_ifaces:
        # dynamically select interfaces from the system to pass to the
        # provisioning command
        _logger.info("Dynamic interface selection enabled")
        ifaces = addc.filtered_interfaces(domconfig.interface_config)
        _logger.info("Selected interfaces: %s", ifaces)
        prov_opts.append(("interfaces", " ".join(ifaces)))
        prov_opts.append(("bind interfaces only", "yes"))
    addc.provision(
        realm=domconfig.realm,
        domain=domconfig.short_domain,
        dcname=dcname,
        admin_password=domconfig.admin_password,
        options=prov_opts,
    )
    _merge_config(_provisioned, ctx.instance_config.global_options())


def _prep_join(ctx: Context) -> None:
    if os.path.exists(_provisioned):
        _logger.info("Already configured. Not joining")
        return
    domconfig = ctx.instance_config.domain()
    _logger.info(f"Provisioning domain: {domconfig.realm}")

    dcname = ctx.cli.name or domconfig.dcname
    addc.join(
        realm=domconfig.realm,
        domain=domconfig.short_domain,
        dcname=dcname,
        admin_password=domconfig.admin_password,
        options=ctx.instance_config.global_options(),
    )
    _merge_config(_provisioned, ctx.instance_config.global_options())


def _merge_config(
    smb_conf_path: str,
    options: typing.Optional[typing.Iterable[tuple[str, str]]] = None,
) -> None:
    if not options:
        return
    txt_conf = smbconf_samba.SMBConf.from_file(smb_conf_path)
    tmp_conf = smbconf_api.SimpleConfigStore()
    tmp_conf.import_smbconf(txt_conf)
    global_section = dict(tmp_conf["global"])
    global_section.update(options)
    tmp_conf["global"] = list(global_section.items())
    try:
        os.rename(smb_conf_path, f"{smb_conf_path}.orig")
    except OSError:
        pass
    with open(smb_conf_path, "w") as fh:
        smbconf_api.write_store_as_smb_conf(fh, tmp_conf)


def _prep_wait_on_domain(ctx: Context) -> None:
    if not _DNS:
        _logger.info("Can not query domain. Exiting.")
        raise Fail("no dns support available (missing dnsypthon)")

    realm = ctx.instance_config.domain().realm
    waiter = best_waiter(max_timeout=30)
    while True:
        _logger.info(f"checking for AD domain in dns: {realm}")
        try:
            dns.resolver.query(f"_ldap._tcp.{realm}.", "SRV")
            return
        except dns.exception.DNSException:
            _logger.info(f"dns record for {realm} not found")
            waiter.wait()


def _prep_populate(ctx: Context) -> None:
    if os.path.exists(_populated):
        _logger.info("populated marker exists")
        return
    _logger.info("Populating domain with default entries")

    for ou in ctx.instance_config.organizational_units():
        addc.create_ou(ou.ou_name)

    for dgroup in ctx.instance_config.domain_groups():
        addc.create_group(dgroup.groupname, dgroup.ou)

    for duser in ctx.instance_config.domain_users():
        addc.create_user(
            name=duser.username,
            password=duser.plaintext_passwd,
            surname=duser.surname,
            given_name=duser.given_name,
            ou=duser.ou,
        )
        # TODO: probably should improve this to avoid extra calls / loops
        for gname in duser.member_of:
            addc.add_group_members(group_name=gname, members=[duser.username])

    # "touch" the populated marker
    with open(_populated, "w"):
        pass


def _prep_krb5_conf(ctx: Context) -> None:
    shutil.copy("/var/lib/samba/private/krb5.conf", "/etc/krb5.conf")


@dccommands.command(name="run", arg_func=_run_container_args)
def run(ctx: Context) -> None:
    _logger.info("Running AD DC container")
    if _dosetup(ctx, "wait-domain"):
        _prep_wait_on_domain(ctx)
    if _dosetup(ctx, "join"):
        _prep_join(ctx)
    if _dosetup(ctx, "provision"):
        _prep_provision(ctx)
    if _dosetup(ctx, "populate"):
        _prep_populate(ctx)

    _prep_krb5_conf(ctx)
    _logger.info("Starting samba server")
    samba_cmds.execute(samba_cmds.samba_dc_foreground())
