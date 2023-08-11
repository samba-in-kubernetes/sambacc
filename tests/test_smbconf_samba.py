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

import pytest

import sambacc.smbconf_api
import sambacc.smbconf_samba

smb_conf_reg_stub = """
[global]
cache directory = {path}
state directory = {path}
private dir = {path}
include = registry
"""

smb_conf_sample = """
[global]
  realm = my.kingdom.fora.horse

[share_a]
  path = /foo/bar/baz
  read only = no
[share_b]
  path = /foo/x/b
  read only = no
[share_c]
  path = /foo/x/c
  read only = no
[share_d]
  path = /foo/x/d
  read only = no
[share_e]
  path = /foo/x/e
  read only = no
"""


def _import_probe():
    try:
        import samba.smbconf  # type: ignore
        import samba.samba3.smbconf  # type: ignore # noqa
    except ImportError:
        pytest.skip("unable to load samba smbconf modules")


def _smb_data(path, smb_conf_text):
    data_path = path / "_samba"
    data_path.mkdir()
    smb_conf_path = path / "smb.conf"
    smb_conf_path.write_text(smb_conf_text.format(path=data_path))
    return smb_conf_path


@pytest.fixture(scope="session")
def smbconf_reg_once(tmp_path_factory):
    _import_probe()
    tmp_path = tmp_path_factory.mktemp("smb_reg")
    smb_conf_path = _smb_data(tmp_path, smb_conf_reg_stub)

    return sambacc.smbconf_samba.SMBConf.from_registry(str(smb_conf_path))


@pytest.fixture(scope="function")
def smbconf_reg(smbconf_reg_once):
    # IMPORTANT: Reminder, samba doesn't release the registry db once opened.
    smbconf_reg_once._smbconf.drop()
    return smbconf_reg_once


@pytest.fixture(scope="function")
def smbconf_file(tmp_path):
    _import_probe()
    smb_conf_path = _smb_data(tmp_path, smb_conf_sample)

    return sambacc.smbconf_samba.SMBConf.from_file(str(smb_conf_path))


def test_smbconf_file_read(smbconf_file):
    assert smbconf_file["global"] == [("realm", "my.kingdom.fora.horse")]
    assert smbconf_file["share_a"] == [
        ("path", "/foo/bar/baz"),
        ("read only", "no"),
    ]
    with pytest.raises(KeyError):
        smbconf_file["not_there"]
    assert list(smbconf_file) == [
        "global",
        "share_a",
        "share_b",
        "share_c",
        "share_d",
        "share_e",
    ]


def test_smbconf_write(smbconf_file):
    assert not smbconf_file.writeable
    with pytest.raises(Exception):
        smbconf_file.import_smbconf(sambacc.smbconf_api.SimpleConfigStore())


def test_smbconf_reg_write_read(smbconf_reg):
    assert smbconf_reg.writeable
    assert list(smbconf_reg) == []
    smbconf_reg["global"] = [("test:one", "1"), ("test:two", "2")]
    assert smbconf_reg["global"] == [("test:one", "1"), ("test:two", "2")]
    smbconf_reg["global"] = [("test:one", "1"), ("test:two", "22")]
    assert smbconf_reg["global"] == [("test:one", "1"), ("test:two", "22")]


def test_smbconf_reg_write_txn_read(smbconf_reg):
    assert smbconf_reg.writeable
    assert list(smbconf_reg) == []
    with smbconf_reg:
        smbconf_reg["global"] = [("test:one", "1"), ("test:two", "2")]
    assert smbconf_reg["global"] == [("test:one", "1"), ("test:two", "2")]
    with smbconf_reg:
        smbconf_reg["global"] = [("test:one", "1"), ("test:two", "22")]
    assert smbconf_reg["global"] == [("test:one", "1"), ("test:two", "22")]

    # transaction with error
    with pytest.raises(ValueError):
        with smbconf_reg:
            smbconf_reg["global"] = [("test:one", "1"), ("test:two", "2222")]
            raise ValueError("foo")
    assert smbconf_reg["global"] == [("test:one", "1"), ("test:two", "22")]

    # no transaction with error
    with pytest.raises(ValueError):
        smbconf_reg["global"] = [("test:one", "1"), ("test:two", "2222")]
        raise ValueError("foo")
    assert smbconf_reg["global"] == [("test:one", "1"), ("test:two", "2222")]


def test_smbconf_reg_import_batched(smbconf_reg, smbconf_file):
    assert list(smbconf_reg) == []
    smbconf_reg.import_smbconf(smbconf_file, batch_size=4)
    assert smbconf_reg["global"] == [("realm", "my.kingdom.fora.horse")]
    assert smbconf_reg["share_a"] == [
        ("path", "/foo/bar/baz"),
        ("read only", "no"),
    ]
    with pytest.raises(KeyError):
        smbconf_reg["not_there"]
    assert list(smbconf_reg) == [
        "global",
        "share_a",
        "share_b",
        "share_c",
        "share_d",
        "share_e",
    ]


def test_smbconf_reg_import_unbatched(smbconf_reg, smbconf_file):
    assert list(smbconf_reg) == []
    smbconf_reg.import_smbconf(smbconf_file, batch_size=None)
    assert smbconf_reg["global"] == [("realm", "my.kingdom.fora.horse")]
    assert smbconf_reg["share_a"] == [
        ("path", "/foo/bar/baz"),
        ("read only", "no"),
    ]
    with pytest.raises(KeyError):
        smbconf_reg["not_there"]
    assert list(smbconf_reg) == [
        "global",
        "share_a",
        "share_b",
        "share_c",
        "share_d",
        "share_e",
    ]
