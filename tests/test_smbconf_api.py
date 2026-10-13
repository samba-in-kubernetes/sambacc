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

import pytest

import sambacc.smbconf_api
import sambacc.config


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


_sample_config = {
    "samba-container-config": "v0",
    "configs": {
        "test": {
            "shares": ["share1", "share2"],
            "globals": ["g0"],
        }
    },
    "shares": {
        "share1": {
            "options": {
                "path": "/srv/s1",
                "read only": "no",
            }
        },
        "share2": {
            "options": {
                "path": "/srv/s2",
                "guest ok": "yes",
            }
        },
    },
    "globals": {
        "g0": {
            "options": {
                "workgroup": "TESTWG",
                "server string": "test server",
            }
        }
    },
}


def _make_iconfig():
    gc = sambacc.config.GlobalConfig(
        initial_data=_sample_config,
    )
    return gc.get("test")


def test_instance_config_store_iter():
    iconfig = _make_iconfig()
    store = sambacc.smbconf_api.InstanceConfigStore(iconfig)
    assert list(store) == ["global", "share1", "share2"]


def test_instance_config_store_getitem_global():
    iconfig = _make_iconfig()
    store = sambacc.smbconf_api.InstanceConfigStore(iconfig)
    global_opts = store["global"]
    assert ("workgroup", "TESTWG") in global_opts
    assert ("server string", "test server") in global_opts


def test_instance_config_store_getitem_share():
    iconfig = _make_iconfig()
    store = sambacc.smbconf_api.InstanceConfigStore(iconfig)
    opts = store["share1"]
    assert ("path", "/srv/s1") in opts
    assert ("read only", "no") in opts


def test_instance_config_store_getitem_missing():
    iconfig = _make_iconfig()
    store = sambacc.smbconf_api.InstanceConfigStore(iconfig)
    with pytest.raises(KeyError):
        store["nonexistent"]


def test_instance_config_store_not_writeable():
    iconfig = _make_iconfig()
    store = sambacc.smbconf_api.InstanceConfigStore(iconfig)
    assert not store.writeable


def test_instance_config_store_setitem_raises():
    iconfig = _make_iconfig()
    store = sambacc.smbconf_api.InstanceConfigStore(iconfig)
    with pytest.raises(NotImplementedError):
        store["foo"] = [("a", "b")]


def test_instance_config_store_import_to_simple():
    iconfig = _make_iconfig()
    src = sambacc.smbconf_api.InstanceConfigStore(iconfig)
    dst = sambacc.smbconf_api.SimpleConfigStore()
    dst.import_smbconf(src)
    assert list(dst) == ["global", "share1", "share2"]
    assert dst["global"] == [
        ("workgroup", "TESTWG"),
        ("server string", "test server"),
    ]
    assert dst["share1"] == [("path", "/srv/s1"), ("read only", "no")]
    assert dst["share2"] == [("path", "/srv/s2"), ("guest ok", "yes")]
