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

import io
import time

import sambacc.container_dns


J1 = """
{
  "ref": "example",
  "items": [
    {
      "name": "users",
      "ipv4": "192.168.76.40",
      "target": "external"
    },
    {
      "name": "users-cluster",
      "ipv4": "10.235.102.5",
      "target": "internal"
    }
  ]
}
"""

J2 = """
{
  "ref": "example2",
  "items": [
    {
      "name": "users-cluster",
      "ipv4": "10.235.102.5",
      "target": "internal"
    }
  ]
}
"""

J3 = """
{
  "ref": "example",
  "items": [
    {
      "name": "users",
      "ipv4": "192.168.76.108",
      "target": "external"
    },
    {
      "name": "users-cluster",
      "ipv4": "10.235.102.5",
      "target": "internal"
    }
  ]
}
"""


def test_parse():
    fh = io.StringIO(J1)
    hs = sambacc.container_dns.parse(fh)
    assert hs.ref == "example"
    assert len(hs.items) == 2
    assert hs.items[0].name == "users"
    assert hs.items[0].ipv4_addr == "192.168.76.40"


def test_parse2():
    fh = io.StringIO(J2)
    hs = sambacc.container_dns.parse(fh)
    assert hs.ref == "example2"
    assert len(hs.items) == 1
    assert hs.items[0].name == "users-cluster"
    assert hs.items[0].ipv4_addr == "10.235.102.5"


def test_same():
    hs1 = sambacc.container_dns.HostState(ref="apple")
    hs2 = sambacc.container_dns.HostState(ref="orange")
    assert hs1 != hs2
    hs2 = sambacc.container_dns.HostState(ref="apple")
    assert hs1 == hs2
    hs1.items = [
        sambacc.container_dns.HostInfo("a", "10.10.10.10", "external"),
        sambacc.container_dns.HostInfo("b", "10.10.10.11", "external"),
    ]
    hs2.items = [
        sambacc.container_dns.HostInfo("a", "10.10.10.10", "external"),
        sambacc.container_dns.HostInfo("b", "10.10.10.11", "external"),
    ]
    assert hs1 == hs2
    hs2.items = [
        sambacc.container_dns.HostInfo("a", "10.10.10.10", "external"),
        sambacc.container_dns.HostInfo("b", "10.10.10.12", "external"),
    ]
    assert hs1 != hs2
    hs2.items = [
        sambacc.container_dns.HostInfo("a", "10.10.10.10", "external")
    ]
    assert hs1 != hs2


def test_register_dummy(capfd):
    def register(iconfig, hs):
        return sambacc.container_dns.register(
            iconfig,
            hs,
            prefix=["echo"],
        )

    hs = sambacc.container_dns.HostState(
        ref="example",
        items=[
            sambacc.container_dns.HostInfo(
                "foobar", "10.10.10.10", "external"
            ),
            sambacc.container_dns.HostInfo(
                "blat", "192.168.10.10", "internal"
            ),
        ],
    )
    register("example.test", hs)
    out, err = capfd.readouterr()
    assert "net ads -P dns register foobar.example.test 10.10.10.10" in out


def test_parse_and_update(tmp_path):
    reg_data = []

    def _register(domain, hs, target_name=""):
        reg_data.append((domain, hs))
        return True

    path = tmp_path / "test.json"
    with open(path, "w") as fh:
        fh.write(J1)

    hs1, up = sambacc.container_dns.parse_and_update(
        "example.com", path, reg_func=_register
    )
    assert len(reg_data) == 1
    assert up
    hs2, up = sambacc.container_dns.parse_and_update(
        "example.com", path, previous=hs1, reg_func=_register
    )
    assert len(reg_data) == 1
    assert not up

    with open(path, "w") as fh:
        fh.write(J2)
    hs3, up = sambacc.container_dns.parse_and_update(
        "example.com", path, previous=hs2, reg_func=_register
    )
    assert len(reg_data) == 2
    assert reg_data[-1][1] == hs3
    assert up


def test_watch(tmp_path):
    reg_data = []

    def _register(domain, hs, target_name=""):
        reg_data.append((domain, hs))

    def _update(domain, source, previous=None):
        return sambacc.container_dns.parse_and_update(
            domain, source, previous=previous, reg_func=_register
        )

    scount = 0

    def _sleep():
        nonlocal scount
        scount += 1
        if scount > 10:
            raise KeyboardInterrupt()
        time.sleep(0.05)

    path = tmp_path / "test.json"
    with open(path, "w") as fh:
        fh.write(J1)

    sambacc.container_dns.watch(
        "example.com",
        path,
        update_func=_update,
        pause_func=_sleep,
        print_func=lambda x: None,
    )
    assert scount > 10
    assert len(reg_data) == 1

    with open(path, "w") as fh:
        fh.write(J1)
    scount = 0

    def _sleep2():
        nonlocal scount
        scount += 1
        if scount == 5:
            with open(path, "w") as fh:
                fh.write(J3)
        if scount == 10:
            with open(path, "w") as fh:
                fh.write(J3)
        if scount > 20:
            raise KeyboardInterrupt()
        time.sleep(0.05)

    sambacc.container_dns.watch(
        "example.com",
        path,
        update_func=_update,
        pause_func=_sleep2,
        print_func=lambda x: None,
    )
    assert scount > 20
    assert len(reg_data) == 3
