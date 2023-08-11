#
# sambacc: a samba container configuration tool
# Copyright (C) 2023  John Mulligan
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

import sambacc.smbconf_api


def test_simple_config_store():
    scs = sambacc.smbconf_api.SimpleConfigStore()
    assert scs.writeable, "SimpleConfigStore should always be writeable"
    scs["foo"] = [("a", "Artichoke"), ("b", "Broccoli")]
    scs["bar"] = [("example", "yes"), ("production", "no")]
    assert list(scs) == ["foo", "bar"]
    assert scs["foo"] == [("a", "Artichoke"), ("b", "Broccoli")]
    assert scs["bar"] == [("example", "yes"), ("production", "no")]


def test_simple_config_store_import():
    a = sambacc.smbconf_api.SimpleConfigStore()
    b = sambacc.smbconf_api.SimpleConfigStore()
    a["foo"] = [("a", "Artichoke"), ("b", "Broccoli")]
    b["bar"] = [("example", "yes"), ("production", "no")]
    assert list(a) == ["foo"]
    assert list(b) == ["bar"]

    a.import_smbconf(b)
    assert list(a) == ["foo", "bar"]
    assert list(b) == ["bar"]
    assert a["bar"] == [("example", "yes"), ("production", "no")]

    b["baz"] = [("quest", "one")]
    b["bar"] = [("example", "no"), ("production", "no"), ("unittest", "yes")]
    a.import_smbconf(b)

    assert list(a) == ["foo", "bar", "baz"]
    assert a["bar"] == [
        ("example", "no"),
        ("production", "no"),
        ("unittest", "yes"),
    ]
    assert a["baz"] == [("quest", "one")]


def test_write_store_as_smb_conf():
    scs = sambacc.smbconf_api.SimpleConfigStore()
    scs["foo"] = [("a", "Artichoke"), ("b", "Broccoli")]
    scs["bar"] = [("example", "yes"), ("production", "no")]
    scs["global"] = [("first", "1"), ("second", "2")]
    fh = io.StringIO()
    sambacc.smbconf_api.write_store_as_smb_conf(fh, scs)
    res = fh.getvalue().splitlines()
    assert res[0] == ""
    assert res[1] == "[global]"
    assert res[2] == "\tfirst = 1"
    assert res[3] == "\tsecond = 2"
    assert "[foo]" in res
    assert "\ta = Artichoke" in res
    assert "\tb = Broccoli" in res
    assert "[bar]" in res
    assert "\texample = yes" in res
    assert "\tproduction = no" in res
