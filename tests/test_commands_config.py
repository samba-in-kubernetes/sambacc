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

import argparse
import functools
import os

import sambacc.config
import sambacc.opener
import sambacc.paths

import sambacc.commands.config


config1 = """
{
    "samba-container-config": "v0",
    "configs": {
        "updateme":{
          "shares": ["uno"],
          "globals": ["global0"]
        }
    },
    "shares": {
       "uno": {
          "options": {
              "path": "/srv/data/uno"
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
        "updateme":{
          "shares": ["uno", "dos"],
          "globals": ["global0"],
          "permissions": {"method": "none"}
        }
    },
    "shares": {
       "uno": {
          "options": {
              "path": "/srv/data/uno"
          }
       },
       "dos": {
          "options": {
              "path": "/srv/data/dos"
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


class FakeContext:
    cli: argparse.Namespace
    instance_config: sambacc.config.InstanceConfig

    def __init__(self, opts, instance_config):
        self.cli = argparse.Namespace()
        self.instance_config = instance_config
        for k, v in opts.items():
            setattr(self.cli, k, v)
        self.require_validation = False

    @classmethod
    def defaults(cls, cfg_path, watch=False):
        with open(cfg_path, "w") as fh:
            fh.write(config1)

        config = [cfg_path]
        identity = "updateme"
        ctx = cls(
            {
                "watch": watch,
                "config": config,
                "identity": identity,
            },
            sambacc.config.read_config_files(config).get(identity),
        )
        return ctx

    @property
    def opener(self) -> sambacc.opener.Opener:
        return sambacc.opener.FileOpener()


class FakeWaiter:
    def __init__(self, attempts=None):
        self.count = 0
        self.on_count = {}
        self.attempts = attempts

    def acted(self):
        pass

    def wait(self):
        if self.attempts is not None and self.count >= self.attempts:
            raise KeyboardInterrupt()
        wf = self.on_count.get(self.count, None)
        if wf is not None:
            wf()
        self.count += 1


def _gen_fake_cmd(fake_path, chkpath, pnn="0"):
    with open(fake_path, "w") as fh:
        fh.write("#!/bin/sh\n")
        fh.write(f'echo "$@" >> {chkpath}\n')
        fh.write(f'[ "$1" = ctdb ] && echo {pnn}" " ; \n')
        fh.write("exit 0\n")
    os.chmod(fake_path, 0o755)


def test_update_config_changed(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path)
    with open(cfg_path, "w") as fh:
        fh.write(config2)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
    assert any(("smbcontrol" in line) for line in chk)


def test_update_config_changed_ctdb(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path)
    ctx.instance_config.iconfig["instance_features"] = ["ctdb"]
    assert ctx.instance_config.with_ctdb
    with open(cfg_path, "w") as fh:
        fh.write(config2)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
    assert any(("smbcontrol" in line) for line in chk)


def test_update_config_ctdb_notleader(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath), pnn="")
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path)
    ctx.instance_config.iconfig["instance_features"] = ["ctdb"]
    assert ctx.instance_config.with_ctdb
    with open(cfg_path, "w") as fh:
        fh.write(config2)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert not any(("net" in line) for line in chk)
    assert not any(("smbcontrol" in line) for line in chk)


def test_update_config_watch_waiter_expires(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    fake_waiter = FakeWaiter(attempts=5)

    def _fake_waiter(*args, **kwargs):
        return fake_waiter

    monkeypatch.setattr(sambacc.commands.config, "best_waiter", _fake_waiter)

    ctx = FakeContext.defaults(cfg_path, watch=True)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    sambacc.commands.config.update_config(ctx)

    assert not os.path.exists(chkpath)
    assert fake_waiter.count == 5


def test_update_config_watch_waiter_trigger3(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    fake_waiter = FakeWaiter(attempts=5)

    def _fake_waiter(*args, **kwargs):
        return fake_waiter

    def _new_conf():
        with open(cfg_path, "w") as fh:
            fh.write(config2)

    monkeypatch.setattr(sambacc.commands.config, "best_waiter", _fake_waiter)
    fake_waiter.on_count[3] = _new_conf

    ctx = FakeContext.defaults(cfg_path, watch=True)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
    assert any(("smbcontrol" in line) for line in chk)
    assert fake_waiter.count == 5
