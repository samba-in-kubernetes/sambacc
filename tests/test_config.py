import io
import os
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
  "_extra_junk": 0
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


def test_read_config(tmpdir):
    fname = tmpdir / "sample.json"
    with open(fname, "w") as fh:
        fh.write(config1)
    sambacc.config.read_config(fname)
