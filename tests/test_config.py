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
import unittest

import pytest

import sambacc.config
import sambacc.opener

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
      "instance_name": "GANDOLPH",
      "permissions": {
          "method": "none"
      }
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
      },
      "permissions": {
          "method": "none"
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

addc_config1 = """
{
  "samba-container-config": "v0",
  "configs": {
    "demo": {
      "instance_features": ["addc"],
      "domain_settings": "sink",
      "instance_name": "dc1"
    }
  },
  "domain_settings": {
    "sink": {
      "realm": "DOMAIN1.SINK.TEST",
      "short_domain": "DOMAIN1",
      "admin_password": "Passw0rd"
    }
  },
  "domain_groups": {
    "sink": [
      {"name": "friends"},
      {"name": "gothamites"}
    ]
  },
  "domain_users": {
    "sink": [
      {
        "name": "bwayne",
        "password": "1115Rose.",
        "given_name": "Bruce",
        "surname": "Wayne",
        "member_of": ["friends", "gothamites"]
      },
      {
        "name": "ckent",
        "password": "1115Rose.",
        "given_name": "Clark",
        "surname": "Kent",
        "member_of": ["friends"]
      }
    ]
  }
}
"""

addc_config2 = """
{
  "samba-container-config": "v0",
  "configs": {
    "demo": {
      "instance_features": ["addc"],
      "domain_settings": "sink",
      "instance_name": "dc1"
    }
  },
  "domain_settings": {
    "sink": {
      "realm": "DOMAIN1.SINK.TEST",
      "short_domain": "DOMAIN1",
      "admin_password": "Passw0rd"
    }
  },
  "organizational_units": {
    "sink": [
      {"name": "friends"}
    ]
  },
  "domain_groups": {
    "sink": [
      {
        "name": "friends",
        "ou": "friends"
      },
      {"name": "gothamites"}
    ]
  },
  "domain_users": {
    "sink": [
      {
        "name": "bwayne",
        "password": "1115Rose.",
        "given_name": "Bruce",
        "surname": "Wayne",
        "member_of": ["friends", "gothamites"],
        "ou": "friends"
      },
      {
        "name": "ckent",
        "password": "1115Rose.",
        "given_name": "Clark",
        "surname": "Kent",
        "member_of": ["friends"],
        "ou": "friends"
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

    def test_get_share_paths(self):
        fh = io.StringIO(config1)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        shares = list(ic.shares())
        for share in shares:
            if share.name == "demo":
                assert share.path() == "/mnt/demo"
            elif share.name == "stuff":
                assert share.path() == "/mnt/stuff"
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
    def err_open(*args):
        raise OSError("test!")

    monkeypatch.setattr(sambacc.opener.FileOpener, "open", err_open)
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
    assert "cluster_meta_uri" in cfg
    assert "nodes_path" in cfg
    assert "log_level" in cfg


def test_ad_dc_config_demo():
    c1 = sambacc.config.GlobalConfig(io.StringIO(addc_config1))
    i1 = c1.get("demo")
    assert i1.with_addc

    domcfg = i1.domain()
    assert domcfg.realm == "DOMAIN1.SINK.TEST"
    assert domcfg.short_domain == "DOMAIN1"
    assert domcfg.dcname == "dc1"

    dgroups = sorted(i1.domain_groups(), key=lambda v: v.groupname)
    assert len(dgroups) == 2
    assert dgroups[0].groupname == "friends"

    dusers = sorted(i1.domain_users(), key=lambda v: v.username)
    assert len(dusers) == 2
    assert dusers[0].username == "bwayne"


def test_ad_dc_ou_config_demo():
    c1 = sambacc.config.GlobalConfig(io.StringIO(addc_config2))
    i1 = c1.get("demo")
    assert i1.with_addc

    domou = sorted(i1.organizational_units(), key=lambda v: v.ou_name)
    assert len(domou) == 1
    assert domou[0].ou_name == "friends"

    dgroups = sorted(i1.domain_groups(), key=lambda v: v.groupname)
    assert len(dgroups) == 2
    assert dgroups[0].ou == "friends"

    dusers = sorted(i1.domain_users(), key=lambda v: v.username)
    assert len(dusers) == 2
    assert dusers[0].ou == "friends"


def test_ad_dc_invalid():
    c1 = sambacc.config.GlobalConfig(io.StringIO(config1))
    i1 = c1.get("foobar")
    assert not i1.with_addc

    with pytest.raises(ValueError):
        i1.domain()

    with pytest.raises(ValueError):
        list(i1.domain_users())

    with pytest.raises(ValueError):
        list(i1.domain_groups())

    with pytest.raises(ValueError):
        list(i1.organizational_units())


def test_share_config_no_path():
    j = """{
    "samba-container-config": "v0",
    "configs": {
        "foobar":{
          "shares": ["flunk"],
          "globals": ["global0"]
        }
    },
    "shares": {
       "flunk": {
          "options": {}
       }
    },
    "globals": {
        "global0": {
           "options": {
             "server min protocol": "SMB2"
           }
        }
    }
}"""
    fh = io.StringIO(j)
    g = sambacc.config.GlobalConfig(fh)
    ic = g.get("foobar")
    shares = list(ic.shares())
    assert len(shares) == 1
    assert shares[0].path() is None


@pytest.mark.parametrize(
    "json_a,json_b,iname,expect_equal",
    [
        (config1, config1, "foobar", True),
        (addc_config1, addc_config1, "demo", True),
        (config1, config2, "foobar", False),
        (
            """{
    "samba-container-config": "v0",
    "configs": {
        "foobar":{
          "shares": ["flunk"],
          "globals": ["global0"]
        }
    },
    "shares": {
       "flunk": {
          "options": {"path": "/mnt/yikes"}
       }
    },
    "globals": {
        "global0": {
           "options": {
             "server min protocol": "SMB2"
           }
        }
    }
}""",
            """{
    "samba-container-config": "v0",
    "configs": {
        "foobar":{
          "shares": ["flunk"],
          "globals": ["global0"]
        }
    },
    "shares": {
       "flunk": {
          "options": {"path": "/mnt/psych"}
       }
    },
    "globals": {
        "global0": {
           "options": {
             "server min protocol": "SMB2"
           }
        }
    }
}""",
            "foobar",
            False,
        ),
        (
            """{
    "samba-container-config": "v0",
    "configs": {
        "foobar":{
          "shares": ["flunk"],
          "globals": ["global0"]
        }
    },
    "shares": {
       "flunk": {
          "options": {"path": "/mnt/yikes"}
       }
    },
    "globals": {
        "global0": {
           "options": {
             "server min protocol": "SMB2"
           }
        }
    }
}""",
            """{
    "samba-container-config": "v0",
    "configs": {
        "foobar":{
          "shares": ["flunk"],
          "globals": ["global0"]
        }
    },
    "shares": {
       "flunk": {
          "options": {"path": "/mnt/yikes"}
       }
    },
    "globals": {
        "global0": {
           "options": {
             "server min protocol": "SMB1"
           }
        }
    }
}""",
            "foobar",
            False,
        ),
    ],
    # setting ID to a numeric range makes it a lot easier to read the
    # output on the console, versus having pytest plop two large json
    # blobs for each "row" of inputs
    ids=iter(range(100)),
)
def test_instance_config_equality(json_a, json_b, iname, expect_equal):
    gca = sambacc.config.GlobalConfig(io.StringIO(json_a))
    gcb = sambacc.config.GlobalConfig(io.StringIO(json_b))
    instance_a = gca.get(iname)
    instance_b = gcb.get(iname)
    if expect_equal:
        assert instance_a == instance_b
    else:
        assert instance_a != instance_b


def test_permissions_config_default():
    c1 = sambacc.config.GlobalConfig(io.StringIO(config1))
    ic = c1.get("foobar")
    for share in ic.shares():
        assert share.permissions_config().method == "none"


def test_permissions_config_instance():
    c2 = sambacc.config.GlobalConfig(io.StringIO(config2))
    ic = c2.get("foobar")
    # TODO: improve test to ensure this isn't getting the default.  it does
    # work as designed based on coverage, but we shouldn't rely on that
    for share in ic.shares():
        assert share.permissions_config().method == "none"


def test_permissions_config_share():
    c3 = sambacc.config.GlobalConfig(io.StringIO(config3))
    ic = c3.get("foobar")
    # TODO: improve test to ensure this isn't getting the default.  it does
    # work as designed based on coverage, but we shouldn't rely on that
    for share in ic.shares():
        assert share.permissions_config().method == "none"


def test_permissions_config_options():
    pc = sambacc.config.PermissionsConfig(
        {
            "method": "initialize-share-perms",
            "status_xattr": "user.fake-stuff",
            "mode": "0777",
            "friendship": "always",
        }
    )
    opts = pc.options
    assert len(opts) == 2
    assert "mode" in opts
    assert "friendship" in opts


def _can_import_toml():
    """Return true if one valid toml module can be imported.
    Work around importorskip only supporting one module name.
    """
    try:
        __import__("tomllib")
        return True
    except ImportError:
        pass
    try:
        __import__("tomli")
        return True
    except ImportError:
        pass
    return False


@pytest.mark.parametrize(
    "json_str,ok",
    [
        pytest.param("{}", False, id="empty-json"),
        pytest.param('{"samba-container-config":"v0"}', True, id="minimal"),
        pytest.param(
            """
{
    "samba-container-config": "v0",
    "configs": {
        "foobar": {
            "shares": [
                "foobar"
            ]
        }
    },
    "shares": {
        "foobar": {
            "options": {
                "a": "b"
            }
        }
    }
}
        """,
            True,
            id="one-share",
        ),
        pytest.param(
            """
{
    "samba-container-config": "v0",
    "configs": {
        "foobar": {
            "shares": [
                "foobar"
            ]
        }
    },
    "shares": {
        "foobar": {
            "options": {
                "a": "b"
            }
        }
    },
    "chairs": {"maple": true}
}
        """,
            False,
            id="invalid-section",
        ),
        pytest.param(
            """
{
    "samba-container-config": "v0",
    "configs": {
        "foobar": {
            "shares": [
                "foobar"
            ]
        }
    },
    "shares": {
        "foobar": {
            "options": {
                "a": "b"
            }
        }
    },
    "_chairs": {"maple": true}
}
        """,
            True,
            id="underscore-prefix",
        ),
        pytest.param(
            """
{
    "samba-container-config": "v0",
    "configs": {
        "foobar": {
            "lazlo": "quux",
            "shares": [
                "foobar"
            ]
        }
    },
    "shares": {
        "foobar": {
            "options": {
                "a": "b"
            }
        }
    }
}
        """,
            False,
            id="bad-config-param",
        ),
        pytest.param(
            """
{
    "samba-container-config": "v0",
    "configs": {
        "foobar": {
            "shares": "foobar"
        }
    },
    "shares": {
        "foobar": {
            "options": {
                "a": "b"
            }
        }
    }
}
        """,
            False,
            id="bad-config-type",
        ),
        pytest.param(
            """
{
    "samba-container-config": "v0",
    "configs": {
        "foobar": {
            "shares": [
                "foobar"
            ]
        }
    },
    "shares": {
        "foobar": {
            "blooper": true,
            "options": {
                "a": "b"
            }
        }
    }
}
        """,
            False,
            id="bad-share-prop",
        ),
    ],
)
def test_jsonschema_validation(json_str, ok):
    jsonschema = pytest.importorskip("jsonschema")

    cfg = sambacc.config.GlobalConfig()
    if ok:
        cfg.load(io.StringIO(json_str), require_validation=True)
    else:
        with pytest.raises((ValueError, jsonschema.ValidationError)):
            cfg.load(io.StringIO(json_str), require_validation=True)


@pytest.mark.parametrize(
    "toml_str,ok",
    [
        pytest.param("", False, id="empty"),
        pytest.param("#####FOO", False, id="just-a-comment"),
        pytest.param(
            """
samba-container-config = "v0"
""",
            True,
            id="minimal",
        ),
        pytest.param(
            """
samba-container-config = "v0"

# Define configurations
[configs.foobar]
shares = ["foobar"]

# Define share options
[shares.foobar.options]
a = "b"
""",
            True,
            id="one-share",
        ),
    ],
)
@pytest.mark.skipif(not _can_import_toml(), reason="no toml module")
def test_toml_configs_no_validation(toml_str, ok):
    cfg = sambacc.config.GlobalConfig()
    fh = io.BytesIO(toml_str.encode("utf8"))
    if ok:
        cfg.load(
            fh,
            require_validation=False,
            config_format=sambacc.config.ConfigFormat.TOML,
        )
    else:
        with pytest.raises(ValueError):
            cfg.load(
                fh,
                require_validation=False,
                config_format=sambacc.config.ConfigFormat.TOML,
            )


@pytest.mark.parametrize(
    "toml_str,ok",
    [
        pytest.param("", False, id="empty"),
        pytest.param("#####FOO", False, id="just-a-comment"),
        pytest.param(
            """
samba-container-config = "v0"
""",
            True,
            id="minimal",
        ),
        pytest.param(
            """
samba-container-config = "v0"

# Define configurations
[configs.foobar]
shares = ["foobar"]

# Define share options
[shares.foobar.options]
a = "b"
""",
            True,
            id="one-share",
        ),
        pytest.param(
            """
samba-container-config = "v0"

# Define configurations
[configs.foobar]
shares = ["foobar"]
instance_features = "Kibbe"

# Define share options
[shares.foobar.options]
a = "b"
""",
            False,
            id="bad-instance_features",
        ),
        pytest.param(
            """
samba-container-config = "v0"

# Define configurations
[configs.foobar]
shares = ["foobar"]
instance_features = ["ctdb"]

# Define share options
[shares.foobar.options]
a = "b"
""",
            True,
            id="ok-instance_features",
        ),
        pytest.param(
            """
samba-container-config = "v0"

[configs.demo]
shares = ["share"]
globals = ["default"]
instance_features = ["ctdb"]
instance_name = "SAMBA"

[shares.share.options]
"path" = "/share"
"read only" = "no"
"valid users" = "sambauser, otheruser"

[globals.default.options]
"security" = "user"
"server min protocol" = "SMB2"
"load printers" = "no"
"printing" = "bsd"
"printcap name" = "/dev/null"
"disable spoolss" = "yes"
"guest ok" = "no"

[[users.all_entries]]
name = "sambauser"
password = "samba"

[[users.all_entries]]
name = "otheruser"
password = "insecure321"
""",
            True,
            id="complex",
        ),
    ],
)
@pytest.mark.skipif(not _can_import_toml(), reason="no toml module")
def test_toml_configs_validation(toml_str, ok):
    jsonschema = pytest.importorskip("jsonschema")

    cfg = sambacc.config.GlobalConfig()
    fh = io.BytesIO(toml_str.encode("utf8"))
    if ok:
        cfg.load(
            fh,
            require_validation=True,
            config_format=sambacc.config.ConfigFormat.TOML,
        )
    else:
        with pytest.raises((ValueError, jsonschema.ValidationError)):
            cfg.load(
                fh,
                require_validation=True,
                config_format=sambacc.config.ConfigFormat.TOML,
            )


@pytest.mark.parametrize(
    "yaml_str,ok",
    [
        pytest.param("", False, id="empty"),
        pytest.param("#####FOO", False, id="just-a-comment"),
        pytest.param(
            """
samba-container-config: "v0"
""",
            True,
            id="minimal",
        ),
        pytest.param(
            """
samba-container-config: "v0"
# Define configurations
configs:
  foobar:
    shares:
      - foobar
shares:
  foobar:
    options:
      a: b
""",
            True,
            id="one-share",
        ),
    ],
)
def test_yaml_configs_no_validation(yaml_str, ok):
    pytest.importorskip("yaml")

    cfg = sambacc.config.GlobalConfig()
    fh = io.BytesIO(yaml_str.encode("utf8"))
    if ok:
        cfg.load(
            fh,
            require_validation=False,
            config_format=sambacc.config.ConfigFormat.YAML,
        )
    else:
        with pytest.raises(ValueError):
            cfg.load(
                fh,
                require_validation=False,
                config_format=sambacc.config.ConfigFormat.YAML,
            )


@pytest.mark.parametrize(
    "yaml_str,ok",
    [
        pytest.param("", False, id="empty"),
        pytest.param("#####FOO", False, id="just-a-comment"),
        pytest.param(
            """
samba-container-config: v0
""",
            True,
            id="minimal",
        ),
        pytest.param(
            """
samba-container-config: v0
# Define configurations
configs:
  foobar:
    shares:
      - foobar
# Define shares
shares:
  foobar:
    options:
      a: b
""",
            True,
            id="one-share",
        ),
        pytest.param(
            """
samba-container-config: v0
configs:
  foobar:
    instance_features: baroof
    shares:
      - foobar
shares:
  foobar:
    options:
      a: b
""",
            False,
            id="bad-instance_features",
        ),
        pytest.param(
            """
samba-container-config: v0
configs:
  foobar:
    instance_features:
      - ctdb
    shares:
      - foobar
shares:
  foobar:
    options:
      a: b
""",
            True,
            id="ok-instance_features",
        ),
        pytest.param(
            """
samba-container-config: "v0"
# Configure our demo instance
configs:
  demo:
    shares: ["share"]
    globals: ["default"]
    instance_features: ["ctdb"]
    instance_name: "SAMBA"
# Configure the share
shares:
  share:
    options:
      "path": "/share"
      "read only": "no"
      "valid users": "sambauser, otheruser"
# Configure globals
globals:
  default:
    options:
      "security": "user"
      "server min protocol": "SMB2"
      "load printers": "no"
      "printing": "bsd"
      "printcap name": "/dev/null"
      "disable spoolss": "yes"
      "guest ok": "no"
# Configure users
users:
  all_entries:
    - {"name": "sambauser", "password": "samba"}
    - {"name": "otheruser", "password": "insecure321"}
    - name: cooluser
      password: snarf
""",
            True,
            id="complex",
        ),
    ],
)
def test_yaml_configs_validation(yaml_str, ok):
    pytest.importorskip("yaml")
    jsonschema = pytest.importorskip("jsonschema")

    cfg = sambacc.config.GlobalConfig()
    fh = io.BytesIO(yaml_str.encode("utf8"))
    if ok:
        cfg.load(
            fh,
            require_validation=True,
            config_format=sambacc.config.ConfigFormat.YAML,
        )
    else:
        with pytest.raises((ValueError, jsonschema.ValidationError)):
            cfg.load(
                fh,
                require_validation=True,
                config_format=sambacc.config.ConfigFormat.YAML,
            )
