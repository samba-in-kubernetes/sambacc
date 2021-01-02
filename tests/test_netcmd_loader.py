import io
import pytest

import sambacc.config
import sambacc.netcmd_loader

smb_conf = """
[global]
cache directory = {path}
state directory = {path}
private dir = {path}
include = registry
"""

config1 = """
{
  "samba-container-config": "v0",
  "configs": {
    "foobar": {
      "shares": [
        "share",
        "stuff"
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


@pytest.fixture(scope="function")
def testloader(tmp_path):
    data_path = tmp_path / "_samba"
    data_path.mkdir()
    smb_conf_path = tmp_path / "smb.conf"
    with open(smb_conf_path, "w") as fh:
        fh.write(smb_conf.format(path=data_path))

    ldr = sambacc.netcmd_loader.NetCmdLoader()
    ldr.cmd_prefix = ["net", "--configfile={}".format(smb_conf_path), "conf"]
    return ldr


def test_import(testloader):
    fh = io.StringIO(config1)
    g = sambacc.config.GlobalConfig(fh)
    testloader.import_config(g.get("foobar"))


def test_current_shares(testloader):
    shares = testloader.current_shares()
    assert len(shares) == 0
    fh = io.StringIO(config1)
    g = sambacc.config.GlobalConfig(fh)
    testloader.import_config(g.get("foobar"))
    shares = testloader.current_shares()
    assert len(shares) == 2
    assert "share" in shares
    assert "stuff" in shares


def test_dump(testloader, tmp_path):
    fh = io.StringIO(config1)
    g = sambacc.config.GlobalConfig(fh)
    testloader.import_config(g.get("foobar"))

    with open(tmp_path / "dump.txt", "w") as fh:
        testloader.dump(fh)
    with open(tmp_path / "dump.txt") as fh:
        dump = fh.read()

    assert "[global]" in dump
    assert "netbios name = GANDOLPH" in dump
    assert "[share]" in dump
    assert "path = /share" in dump
    assert "[stuff]" in dump
    assert "path = /mnt/stuff" in dump


def test_set(testloader, tmp_path):
    testloader.set("global", "client signing", "mandatory")

    with open(tmp_path / "dump.txt", "w") as fh:
        testloader.dump(fh)
    with open(tmp_path / "dump.txt") as fh:
        dump = fh.read()

    assert "[global]" in dump
    assert "client signing = mandatory" in dump


def test_loader_error_set(testloader, tmp_path):
    with pytest.raises(sambacc.netcmd_loader.LoaderError):
        testloader.set("", "", "yikes")
