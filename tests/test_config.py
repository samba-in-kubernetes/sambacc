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
import os
import pytest
import unittest

import sambacc.config

config1 = """
{
    "samba-container-config": "v0",
    "configs": {
        "foobar":{
          "shares": ["demo", "stuff"],
          "globals": ["global0"]
        }
    },
    "shares": {
       "demo": {
          "options": {
              "path": "/mnt/demo"
          }
       },
       "stuff": {
          "options": {
              "path": "/mnt/stuff"
          }
       }
    },
    "globals": {
        "global0": {
           "options": {
             "server min protocol": "SMB2"
           }
        }
    }
}
"""

config2 = """
{
  "samba-container-config": "v0",
  "configs": {
    "foobar": {
      "shares": [
        "share"
      ],
      "globals": ["global0"],
      "instance_name": "GANDOLPH"
    }
  },
  "shares": {
    "share": {
      "options": {
        "path": "/share",
        "read only": "no",
        "valid users": "sambauser",
        "guest ok": "no",
        "force user": "root"
      }
    }
  },
  "globals": {
    "global0": {
      "options": {
        "workgroup": "SAMBA",
        "security": "user",
        "server min protocol": "SMB2",
        "load printers": "no",
        "printing": "bsd",
        "printcap name": "/dev/null",
        "disable spoolss": "yes",
        "guest ok": "no"
      }
    }
  },
  "users": {
      "all_entries": [
        {"name": "bob", "password": "notSoSafe"},
        {"name": "alice", "password": "123fakeStreet"},
        {"name": "carol", "nt_hash": "B784E584D34839235F6D88A5382C3821"}
      ]
  },
  "_extra_junk": 0
}
"""

config3 = """
{
  "samba-container-config": "v0",
  "configs": {
    "foobar": {
      "shares": [
        "share"
      ],
      "globals": ["global0"],
      "instance_name": "RANDOLPH"
    }
  },
  "shares": {
    "share": {
      "options": {
        "path": "/share",
        "read only": "no",
        "valid users": "sambauser",
        "guest ok": "no",
        "force user": "root"
      }
    }
  },
  "globals": {
    "global0": {
      "options": {
        "workgroup": "SAMBA",
        "security": "user",
        "server min protocol": "SMB2",
        "load printers": "no",
        "printing": "bsd",
        "printcap name": "/dev/null",
        "disable spoolss": "yes",
        "guest ok": "no"
      }
    }
  },
  "users": {
      "all_entries": [
        {"name": "bob", "uid": 2000, "gid": 2000,
         "password": "notSoSafe"},
        {"name": "alice","uid": 2001, "gid": 2001,
         "password": "123fakeStreet"},
        {"name": "carol",
         "nt_hash": "B784E584D34839235F6D88A5382C3821"}
      ]
  },
  "groups": {
      "all_entries": [
        {"name": "bobs", "gid": 2000},
        {"name": "alii", "gid": 2001}
      ]
  }
}
"""


ctdb_config1 = """
{
  "samba-container-config": "v0",
  "configs": {
    "ctdb1": {
      "shares": [
        "demo"
      ],
      "globals": [
        "global0"
      ],
      "instance_features": ["ctdb"],
      "instance_name": "ceeteedeebee"
    }
  },
  "shares": {
    "demo": {
      "options": {
        "path": "/share"
      }
    }
  },
  "globals": {
    "global0": {
      "options": {
        "security": "user",
        "load printers": "no",
        "printing": "bsd",
        "printcap name": "/dev/null",
        "disable spoolss": "yes",
        "guest ok": "no"
      }
    }
  },
  "users": {
    "all_entries": [
      {
        "name": "bob",
        "password": "notSoSafe"
      }
    ]
  }
}
"""


class TestConfig(unittest.TestCase):
    def test_non_json(self):
        with self.assertRaises(Exception):
            with open(os.devnull) as fh:
                sambacc.config.GlobalConfig(fh)

    def test_empty_json(self):
        with self.assertRaises(ValueError):
            fh = io.StringIO("{}")
            sambacc.config.GlobalConfig(fh)

    def test_bad_version(self):
        with self.assertRaises(ValueError):
            fh = io.StringIO('{"samba-container-config":"foo"}')
            sambacc.config.GlobalConfig(fh)

    def test_valid_parse(self):
        fh = io.StringIO(config1)
        g = sambacc.config.GlobalConfig(fh)
        assert isinstance(g, sambacc.config.GlobalConfig)

    def test_get_config(self):
        fh = io.StringIO(config1)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        assert len(list(ic.shares())) == 2

    def test_fail_get_config(self):
        fh = io.StringIO(config1)
        g = sambacc.config.GlobalConfig(fh)
        with self.assertRaises(KeyError):
            g.get("wobble")

    def test_get_global_opts(self):
        fh = io.StringIO(config1)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        gopts = list(ic.global_options())
        assert ("server min protocol", "SMB2") in gopts

    def test_get_share_opts(self):
        fh = io.StringIO(config1)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        shares = list(ic.shares())
        for share in shares:
            if share.name == "demo":
                assert ("path", "/mnt/demo") in list(share.share_options())
            elif share.name == "stuff":
                assert ("path", "/mnt/stuff") in list(share.share_options())
            else:
                raise AssertionError(share.name)

    def test_unique_name(self):
        fh = io.StringIO(config2)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        assert ("netbios name", "GANDOLPH") in list(ic.global_options())

    def test_many_global_opts(self):
        fh = io.StringIO(config2)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        assert len(list(ic.global_options())) == (8 + 1)

    def test_some_users(self):
        fh = io.StringIO(config2)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        users = list(ic.users())
        assert len(users) == 3
        assert users[0].username == "bob"
        assert users[0].uid == 1000
        assert users[0].gid == 1000
        pwline = ":".join(users[2].passwd_fields())
        assert pwline == "carol:x:1002:1002::/invalid:/bin/false"

    def test_some_groups(self):
        fh = io.StringIO(config2)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        groups = list(ic.groups())
        assert len(groups) == 3
        assert groups[0].groupname == "bob"
        assert groups[0].gid == 1000

    def test_invalid_user_entry(self):
        rec = {"name": "foo", "uid": "fred"}
        with pytest.raises(ValueError):
            sambacc.config.UserEntry(None, rec, 0)
        rec = {"name": "foo", "uid": 2200, "gid": "beep"}
        with pytest.raises(ValueError):
            sambacc.config.UserEntry(None, rec, 0)

    def test_invalid_group_entry(self):
        rec = {"name": "foo", "gid": "boop"}
        with pytest.raises(ValueError):
            sambacc.config.GroupEntry(None, rec, 0)

    def test_user_entry_fields(self):
        fh = io.StringIO(config2)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        rec = {"name": "jim", "uid": 2200, "gid": 2200}
        ue = sambacc.config.UserEntry(ic, rec, 0)
        assert ue.uid == 2200
        assert ue.gid == 2200
        assert ue.plaintext_passwd == ""

        rec = {"name": "jim", "password": "letmein"}
        ue = sambacc.config.UserEntry(ic, rec, 10)
        assert ue.uid == 1010
        assert ue.gid == 1010
        assert ue.plaintext_passwd == "letmein"

        rec = {"name": "jim", "nt_hash": "544849536973494D504F535349424C45"}
        ue = sambacc.config.UserEntry(ic, rec, 10)
        assert ue.uid == 1010
        assert ue.gid == 1010
        assert ue.plaintext_passwd == ""
        assert ue.nt_passwd == b"THISisIMPOSSIBLE"

    def test_group_entry_fields(self):
        fh = io.StringIO(config2)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")

        rec = {"name": "hackers", "gid": 2200}
        ue = sambacc.config.GroupEntry(ic, rec, 0)
        assert ue.gid == 2200

        rec = {"name": "hackers"}
        ue = sambacc.config.GroupEntry(ic, rec, 20)
        assert ue.gid == 1020

    def test_explicitly_defined_groups(self):
        fh = io.StringIO(config3)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        groups = list(ic.groups())
        assert len(groups) == 3
        assert groups[0].groupname == "bobs"
        assert groups[0].gid == 2000
        assert groups[1].groupname == "alii"
        assert groups[1].gid == 2001
        assert groups[2].groupname == "carol"
        assert groups[2].gid == 1002


def test_read_config_files(tmpdir):
    fname = tmpdir / "sample.json"
    with open(fname, "w") as fh:
        fh.write(config1)
    sambacc.config.read_config_files([fname])


def test_read_config_files_noexist(tmpdir):
    fake1 = tmpdir / "fake1"
    fake2 = tmpdir / "fake2"
    with pytest.raises(ValueError):
        sambacc.config.read_config_files([fake1, fake2])


def test_read_config_files_realerr(tmpdir):
    if os.getuid() == 0:
        pytest.skip("test invalid when uid=0")
    fname = tmpdir / "sample.json"
    with open(fname, "w") as fh:
        fh.write(config1)
    # Prevent reading of the file to test any other error than
    # ENOENT is raised.
    os.chmod(fname, 0o333)
    try:
        with pytest.raises(OSError):
            sambacc.config.read_config_files([fname])
    finally:
        os.unlink(fname)


def test_tesd_config_files_realerr_rootok(monkeypatch):
    def err_open(p):
        raise OSError("test!")

    monkeypatch.setattr(sambacc.config, "_open", err_open)
    fname = "/etc/foobar"
    with pytest.raises(OSError):
        sambacc.config.read_config_files([fname])


def test_instance_with_ctdb():
    c1 = sambacc.config.GlobalConfig(io.StringIO(config1))
    i1 = c1.get("foobar")
    assert not i1.with_ctdb

    c2 = sambacc.config.GlobalConfig(io.StringIO(ctdb_config1))
    i2 = c2.get("ctdb1")
    assert i2.with_ctdb


def test_instance_ctdb_smb_config():
    c1 = sambacc.config.GlobalConfig(io.StringIO(config1))
    i1 = c1.get("foobar")
    with pytest.raises(ValueError):
        i1.ctdb_smb_config()

    c2 = sambacc.config.GlobalConfig(io.StringIO(ctdb_config1))
    i2 = c2.get("ctdb1")
    csc = i2.ctdb_smb_config()
    gopts = dict(csc.global_options())
    assert gopts["clustering"] == "yes"
    assert gopts["include"] == "registry"
    assert csc.shares() == []


def test_instance_ctdb_config():
    c1 = sambacc.config.GlobalConfig(io.StringIO(config1))
    i1 = c1.get("foobar")
    assert i1.ctdb_config() == {}

    c2 = sambacc.config.GlobalConfig(io.StringIO(ctdb_config1))
    i2 = c2.get("ctdb1")
    cfg = i2.ctdb_config()
    assert "nodes_json" in cfg
    assert "nodes_path" in cfg
    assert "log_level" in cfg
