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
import re
import subprocess
import typing

from sambacc import config
from sambacc import samba_cmds

_logger = logging.getLogger(__name__)


def provision(
    realm: str,
    dcname: str,
    admin_password: str,
    dns_backend: typing.Optional[str] = None,
    domain: typing.Optional[str] = None,
    options: typing.Optional[typing.Iterable[tuple[str, str]]] = None,
) -> None:
    # this function is a direct translation of a previous shell script
    # as samba-tool is based on python libs, this function could possibly
    # be converted to import samba's libs and use that.
    _logger.info(f"Provisioning AD domain: realm={realm}")
    subprocess.check_call(
        _provision_cmd(
            realm,
            dcname,
            admin_password=admin_password,
            dns_backend=dns_backend,
            domain=domain,
            options=options,
        )
    )
    return


def join(
    realm: str,
    dcname: str,
    admin_password: str,
    dns_backend: typing.Optional[str] = None,
    domain: typing.Optional[str] = None,
    options: typing.Optional[typing.Iterable[tuple[str, str]]] = None,
) -> None:
    _logger.info(f"Joining AD domain: realm={realm}")
    subprocess.check_call(
        _join_cmd(
            realm,
            dcname,
            admin_password=admin_password,
            dns_backend=dns_backend,
            options=options,
        )
    )


def create_user(
    name: str,
    password: str,
    surname: typing.Optional[str],
    given_name: typing.Optional[str],
    ou: typing.Optional[str] = None,
) -> None:
    cmd = _user_create_cmd(name, password, surname, given_name, ou)
    _logger.info("Creating user: %r", name)
    subprocess.check_call(cmd)


def create_group(name: str, ou: typing.Optional[str] = None) -> None:
    cmd = _group_add_cmd(name, ou)
    _logger.info("Creating group: %r", name)
    subprocess.check_call(cmd)


def create_ou(name: str) -> None:
    cmd = _ou_add_cmd(name)
    _logger.info("Creating organizational unit: %r", name)
    subprocess.check_call(cmd)


def add_group_members(group_name: str, members: list[str]) -> None:
    cmd = _group_add_members_cmd(group_name, members)
    _logger.info("Adding group members: %r", cmd)
    subprocess.check_call(cmd)


def _filter_opts(
    options: typing.Optional[typing.Iterable[tuple[str, str]]]
) -> list[tuple[str, str]]:
    _skip_keys = ["netbios name"]
    options = options or []
    return [(k, v) for (k, v) in options if k not in _skip_keys]


def _provision_cmd(
    realm: str,
    dcname: str,
    admin_password: str,
    dns_backend: typing.Optional[str] = None,
    domain: typing.Optional[str] = None,
    options: typing.Optional[typing.Iterable[tuple[str, str]]] = None,
) -> list[str]:
    if not dns_backend:
        dns_backend = "SAMBA_INTERNAL"
    if not domain:
        domain = realm.split(".")[0].upper()
    cmd = samba_cmds.sambatool[
        "domain",
        "provision",
        f"--option=netbios name={dcname}",
        "--use-rfc2307",
        f"--dns-backend={dns_backend}",
        "--server-role=dc",
        f"--realm={realm}",
        f"--domain={domain}",
        f"--adminpass={admin_password}",
    ]
    cmd = cmd[
        [f"--option={okey}={oval}" for okey, oval in _filter_opts(options)]
    ]
    return cmd.argv()


def _join_cmd(
    realm: str,
    dcname: str,
    admin_password: str,
    dns_backend: typing.Optional[str] = None,
    domain: typing.Optional[str] = None,
    options: typing.Optional[typing.Iterable[tuple[str, str]]] = None,
) -> list[str]:
    if not dns_backend:
        dns_backend = "SAMBA_INTERNAL"
    if not domain:
        domain = realm.split(".")[0].upper()
    cmd = samba_cmds.sambatool[
        "domain",
        "join",
        realm,
        "DC",
        f"-U{domain}\\Administrator",
        f"--option=netbios name={dcname}",
        f"--dns-backend={dns_backend}",
        f"--password={admin_password}",
    ]
    cmd = cmd[
        [f"--option={okey}={oval}" for okey, oval in _filter_opts(options)]
    ]
    return cmd.argv()


def _user_create_cmd(
    name: str,
    password: str,
    surname: typing.Optional[str],
    given_name: typing.Optional[str],
    ou: typing.Optional[str],
) -> list[str]:
    cmd = samba_cmds.sambatool[
        "user",
        "create",
        name,
        password,
    ].argv()
    if surname:
        cmd.append(f"--surname={surname}")
    if given_name:
        cmd.append(f"--given-name={given_name}")
    if ou:
        cmd.append(f"--userou=OU={ou}")
    return cmd


def _group_add_cmd(name: str, ou: typing.Optional[str]) -> list[str]:
    cmd = samba_cmds.sambatool[
        "group",
        "add",
        name,
    ].argv()
    if ou:
        cmd.append(f"--groupou=OU={ou}")
    return cmd


def _ou_add_cmd(name: str) -> list[str]:
    cmd = samba_cmds.sambatool[
        "ou",
        "add",
        f"OU={name}",
    ].argv()
    return cmd


def _group_add_members_cmd(group_name: str, members: list[str]) -> list[str]:
    cmd = samba_cmds.sambatool[
        "group",
        "addmembers",
        group_name,
        ",".join(members),
    ].argv()
    return cmd


def _ifnames() -> list[str]:
    import socket

    return [iface for _, iface in socket.if_nameindex()]


def filtered_interfaces(
    ic: config.DCInterfaceConfig, ifnames: typing.Optional[list[str]] = None
) -> list[str]:
    _include = re.compile(ic.include_pattern or "^.*$")
    _exclude = re.compile(ic.exclude_pattern or "^$")
    if ifnames is None:
        ifnames = _ifnames()
    return [
        name
        for name in ifnames
        if (name == "lo")
        or (_include.match(name) and not _exclude.match(name))
    ]
