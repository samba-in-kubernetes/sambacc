#
# sambacc: a samba container configuration tool
# Copyright (C) 2022  John Mulligan
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

import os

import pytest

import sambacc.addc


def _fake_samba_tool(path):
    fake_samba_tool = path / "fake_samba_tool.sh"
    with open(fake_samba_tool, "w") as fh:
        fh.write("#!/bin/sh\n")
        fh.write(f"[ -e {path}/fail ] && exit 1\n")
        fh.write(f'echo "$@" > {path}/args.out\n')
        fh.write("exit 0")
    os.chmod(fake_samba_tool, 0o700)
    return fake_samba_tool


def test_provision(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sambacc.samba_cmds, "_GLOBAL_PREFIX", [_fake_samba_tool(tmp_path)]
    )

    sambacc.addc.provision("FOOBAR.TEST", "quux", "h4ckm3")
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "--realm=FOOBAR.TEST" in result
    assert "--option=netbios name=quux" in result
    assert "--dns-backend=SAMBA_INTERNAL" in result

    sambacc.addc.provision(
        "BARFOO.TEST",
        "quux",
        "h4ckm3",
        options=[
            ("ldap server require strong auth", "no"),
            ("dns zone scavenging", "yes"),
            ("ldap machine suffix", "ou=Machines"),
            ("netbios name", "flipper"),
        ],
    )
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "--realm=BARFOO.TEST" in result
    assert "--option=netbios name=quux" in result
    assert "--dns-backend=SAMBA_INTERNAL" in result
    assert "--option=ldap server require strong auth=no" in result
    assert "--option=dns zone scavenging=yes" in result
    assert "--option=ldap machine suffix=ou=Machines" in result
    assert "--option=netbios name=flipper" not in result

    open(tmp_path / "fail", "w").close()
    with pytest.raises(Exception):
        sambacc.addc.provision("FOOBAR.TEST", "quux", "h4ckm3")


def test_join(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sambacc.samba_cmds, "_GLOBAL_PREFIX", [_fake_samba_tool(tmp_path)]
    )

    sambacc.addc.join("FOOBAR.TEST", "quux", "h4ckm3")
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "FOOBAR.TEST" in result
    assert "--option=netbios name=quux" in result
    assert "--dns-backend=SAMBA_INTERNAL" in result

    sambacc.addc.join(
        "BARFOO.TEST",
        "quux",
        "h4ckm3",
        options=[
            ("ldap server require strong auth", "no"),
            ("dns zone scavenging", "yes"),
            ("ldap machine suffix", "ou=Machines"),
            ("netbios name", "flipper"),
        ],
    )
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "BARFOO.TEST" in result
    assert "--option=netbios name=quux" in result
    assert "--dns-backend=SAMBA_INTERNAL" in result
    assert "--option=ldap server require strong auth=no" in result
    assert "--option=dns zone scavenging=yes" in result
    assert "--option=ldap machine suffix=ou=Machines" in result
    assert "--option=netbios name=flipper" not in result


def test_create_user(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sambacc.samba_cmds, "_GLOBAL_PREFIX", [_fake_samba_tool(tmp_path)]
    )

    sambacc.addc.create_user("fflintstone", "b3dr0ck", "Flintstone", "Fred")
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "user create fflintstone" in result
    assert "--surname=Flintstone" in result
    assert "--given-name=Fred" in result


def test_create_ou(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sambacc.samba_cmds, "_GLOBAL_PREFIX", [_fake_samba_tool(tmp_path)]
    )

    sambacc.addc.create_ou("quarry_workers")
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "ou add OU=quarry_workers" in result


def test_create_group(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sambacc.samba_cmds, "_GLOBAL_PREFIX", [_fake_samba_tool(tmp_path)]
    )

    sambacc.addc.create_group("quarry_workers")
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "group add quarry_workers" in result


def test_add_group_members(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sambacc.samba_cmds, "_GLOBAL_PREFIX", [_fake_samba_tool(tmp_path)]
    )

    sambacc.addc.add_group_members(
        "quarry_workers", ["fflintstone", "brubble"]
    )
    with open(tmp_path / "args.out") as fh:
        result = fh.read()
    assert "group addmembers quarry_workers" in result
    assert "fflintstone,brubble" in result


@pytest.mark.parametrize(
    "cfg,ifaces,expected",
    [
        ({}, ["foo", "bar"], None),
        (
            {"include_pattern": "^eth.*$"},
            ["lo", "eth0", "eth1", "biff1"],
            ["lo", "eth0", "eth1"],
        ),
        (
            {"include_pattern": "^nope$"},
            ["lo", "eth0", "eth1", "biff1"],
            ["lo"],
        ),
        (
            {"include_pattern": "^biff[0-9]+$"},
            ["lo", "eth0", "eth1", "biff1"],
            ["lo", "biff1"],
        ),
        (
            {"exclude_pattern": "^docker[0-9]+$"},
            ["lo", "eno1", "eno2", "docker0"],
            ["lo", "eno1", "eno2"],
        ),
        (
            {"exclude_pattern": "^.*$"},
            ["lo", "eno1", "eno2", "docker0"],
            ["lo"],
        ),
        (
            {
                "include_pattern": "^[ed].*$",
                "exclude_pattern": "^docker[0-9]+$",
            },
            ["lo", "eno1", "eno2", "docker0"],
            ["lo", "eno1", "eno2"],
        ),
        (
            {
                "include_pattern": "^[ed].*$",
                "exclude_pattern": "^.*0$",
            },
            ["lo", "dx1f2", "docker0"],
            ["lo", "dx1f2"],
        ),
    ],
)
def test_filtered_interfaces(cfg, ifaces, expected):
    ic = sambacc.config.DCInterfaceConfig(cfg)
    if cfg:
        assert ic.configured
        assert sambacc.addc.filtered_interfaces(ic, ifaces) == expected
    else:
        assert not ic.configured
