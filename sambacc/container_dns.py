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

import json
import subprocess
import typing

from sambacc import samba_cmds

EXTERNAL: str = "external"
INTERNAL: str = "internal"


class HostState:
    def __init__(self, ref="", items=[]):
        self.ref = ref
        self.items = items

    @classmethod
    def from_dict(cls, d):
        return cls(
            ref=d["ref"],
            items=[HostInfo.from_dict(i) for i in d.get("items", [])],
        )

    def __eq__(self, other):
        return (
            self.ref == other.ref
            and len(self.items) == len(other.items)
            and all(s == o for (s, o) in zip(self.items, other.items))
        )


class HostInfo:
    def __init__(self, name="", ipv4_addr="", target=""):
        self.name = name
        self.ipv4_addr = ipv4_addr
        self.target = target

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d["name"],
            ipv4_addr=d["ipv4"],
            target=d.get("target", ""),
        )

    def __eq__(self, other):
        return (
            self.name == other.name
            and self.ipv4_addr == other.ipv4_addr
            and self.target == other.target
        )


def parse(fh):
    return HostState.from_dict(json.load(fh))


def parse_file(path):
    with open(path) as fh:
        return parse(fh)


def match_target(state: HostState, target_name: str) -> typing.List[HostInfo]:
    return [h for h in state.items if h.target == target_name]


def register(domain, hs, prefix=None, target_name: str = EXTERNAL) -> bool:
    updated = False
    for item in match_target(hs, target_name):
        ip = item.ipv4_addr
        fqdn = "{}.{}".format(item.name, domain)
        cmd = samba_cmds.net["ads", "-P", "dns", "register", fqdn, ip]
        if prefix is not None:
            cmd.cmd_prefix = prefix
        subprocess.check_call(list(cmd))
        updated = True
    return updated


def parse_and_update(
    domain: str,
    source: str,
    previous: typing.Optional[HostState] = None,
    target_name: str = EXTERNAL,
    reg_func=register,
) -> typing.Tuple[HostState, bool]:
    hs = parse_file(source)
    if previous is not None and hs == previous:
        # no changes
        return hs, False
    updated = reg_func(domain, hs, target_name=target_name)
    return hs, updated


# TODO: replace this with the common version added to simple_waiter
def watch(domain, source, update_func, pause_func, print_func=None):
    previous = None
    while True:
        try:
            previous, updated = update_func(domain, source, previous)
        except FileNotFoundError:
            print_func(f"Source file [{source}] not found")
            updated = False
            previous = None
        if updated and print_func:
            print_func("Updating external dns registrations")
        try:
            pause_func()
        except KeyboardInterrupt:
            return
