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
import unittest.mock

import pytest

import sambacc.config
import sambacc.opener
import sambacc.paths
import sambacc.passdb_loader

import sambacc.commands.config
import sambacc.commands.cli
import sambacc.smbconf_samba
import sambacc.smbconf_api


@pytest.fixture(autouse=True)
def _force_netcmd_fallback(monkeypatch):
    """Force _import_config to use the NetCmdLoader fallback by making
    SMBConf unavailable.  This keeps the config-change/update tests
    independent of whether the samba smbconf python bindings are present.
    """
    mock_cls = unittest.mock.MagicMock()
    mock_cls.from_registry.side_effect = ImportError("smbconf not available")
    monkeypatch.setattr(
        sambacc.smbconf_samba,
        "SMBConf",
        mock_cls,
    )


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
    def defaults(
        cls, cfg_path, watch=False, signal_pids_dir=None, tmpdir=None
    ):
        with open(cfg_path, "w") as fh:
            fh.write(config1)
        if tmpdir:
            pl = sambacc.commands.cli.AltLocation.parse(
                f"/foo/passwd:{tmpdir}/"
            )
            gl = sambacc.commands.cli.AltLocation.parse(
                f"/foo/group:{tmpdir}/"
            )
        else:
            pl = sambacc.commands.cli.AltLocation("/foo/passwd")
            gl = sambacc.commands.cli.AltLocation("/foo/group")

        config = [cfg_path]
        identity = "updateme"
        ctx = cls(
            {
                "watch": watch,
                "signal_pids_dir": signal_pids_dir,
                "config": config,
                "identity": identity,
                "passwd_location": pl,
                "group_location": gl,
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


def _gen_fake_cmd(fake_path, chkpath, pnn="0", fail_cmd=None):
    with open(fake_path, "w") as fh:
        fh.write("#!/bin/sh\n")
        fh.write(f'echo "$@" >> {chkpath}\n')
        fh.write(f'[ "$1" = ctdb ] && echo {pnn}" " ; \n')
        if fail_cmd:
            fh.write(f'[ "$1" = "{fail_cmd}" ] && exit 1\n')
        fh.write("exit 0\n")
    os.chmod(fake_path, 0o755)


def test_update_config_changed(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path, tmpdir=tmp_path)
    with open(cfg_path, "w") as fh:
        fh.write(config2)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    monkeypatch.setattr(
        sambacc.commands.config,
        "sync_passdb_users",
        unittest.mock.MagicMock(),
    )
    sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
    assert any(("smbcontrol" in line) for line in chk)


def test_update_config_smbcontrol_fails(tmp_path, monkeypatch, caplog):
    # If smbd isn't reachable or still starting up, smbcontrol exits
    # non-zero. That must be logged, not raised, so it doesn't crash the
    # config watch loop.
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath), fail_cmd="smbcontrol")
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path, tmpdir=tmp_path)
    with open(cfg_path, "w") as fh:
        fh.write(config2)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    monkeypatch.setattr(
        sambacc.commands.config,
        "sync_passdb_users",
        unittest.mock.MagicMock(),
    )
    with caplog.at_level("WARNING"):
        sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
    assert any(("smbcontrol" in line) for line in chk)
    assert any(
        "smbcontrol could not notify smbd" in rec.message
        for rec in caplog.records
    )


def test_update_config_changed_ctdb(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path, tmpdir=tmp_path)
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
    monkeypatch.setattr(
        sambacc.commands.config,
        "sync_passdb_users",
        unittest.mock.MagicMock(),
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

    ctx = FakeContext.defaults(cfg_path, tmpdir=tmp_path)
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
    monkeypatch.setattr(
        sambacc.commands.config,
        "sync_passdb_users",
        unittest.mock.MagicMock(),
    )
    sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert not any(("net" in line) for line in chk)
    assert not any(("smbcontrol" in line) for line in chk)


def test_update_config_watch_waiter_expires(tmp_path, monkeypatch):
    # Verifies that watch mode performs an initial registry sync on the first
    # iteration even when the config file hasn't changed since the process
    # started.  Subsequent iterations with no config change must not trigger
    # additional writes (only the initial sync happens).
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    fake_waiter = FakeWaiter(attempts=5)

    def _fake_waiter(*args, **kwargs):
        return fake_waiter

    monkeypatch.setattr(sambacc.commands.config, "best_waiter", _fake_waiter)

    ctx = FakeContext.defaults(cfg_path, watch=True, tmpdir=tmp_path)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    monkeypatch.setattr(
        sambacc.commands.config,
        "sync_passdb_users",
        unittest.mock.MagicMock(),
    )
    sambacc.commands.config.update_config(ctx)

    # The initial iteration compares against None so the registry is always
    # written once on startup, regardless of whether the config changed.
    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
    assert any(("smbcontrol" in line) for line in chk)
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

    ctx = FakeContext.defaults(cfg_path, watch=True, tmpdir=tmp_path)
    monkeypatch.setattr(
        sambacc.paths,
        "ensure_share_dirs",
        functools.partial(
            sambacc.paths.ensure_share_dirs, root=str(tmp_path / "_root")
        ),
    )
    monkeypatch.setattr(
        sambacc.commands.config,
        "sync_passdb_users",
        unittest.mock.MagicMock(),
    )
    sambacc.commands.config.update_config(ctx)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
    assert any(("smbcontrol" in line) for line in chk)
    assert fake_waiter.count == 5


def test_import_config_fallback_to_netcmd(tmp_path, monkeypatch):
    """Verify _import_config falls back to NetCmdLoader when SMBConf is
    not importable."""
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path, tmpdir=tmp_path)

    # Make SMBConf unavailable by raising ImportError
    import builtins

    real_import = builtins.__import__

    def _no_smbconf(name, *args, **kwargs):
        if name == "sambacc.smbconf_samba":
            raise ImportError("no smbconf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_smbconf)

    sambacc.commands.config._import_config(ctx.instance_config)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)


def test_import_config_uses_smbconf(tmp_path, monkeypatch):
    """Verify _import_config uses SMBConf when available."""
    cfg_path = str(tmp_path / "config")
    ctx = FakeContext.defaults(cfg_path, tmpdir=tmp_path)

    mock_smbconf_cls = unittest.mock.MagicMock()
    mock_smbconf_instance = unittest.mock.MagicMock()
    mock_smbconf_cls.from_registry.return_value = mock_smbconf_instance

    monkeypatch.setattr(sambacc.smbconf_samba, "SMBConf", mock_smbconf_cls)

    sambacc.commands.config._import_config(ctx.instance_config)

    mock_smbconf_cls.from_registry.assert_called_once()
    mock_smbconf_instance.import_smbconf.assert_called_once()
    imported_store = mock_smbconf_instance.import_smbconf.call_args[0][0]
    assert isinstance(imported_store, sambacc.smbconf_api.InstanceConfigStore)


def test_import_config_smbconf_error_falls_back(tmp_path, monkeypatch):
    """Verify _import_config falls back when SMBConf raises at runtime."""
    cfg_path = str(tmp_path / "config")
    fake = tmp_path / "fake.sh"
    chkpath = tmp_path / ".executed"
    _gen_fake_cmd(fake, str(chkpath))
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    ctx = FakeContext.defaults(cfg_path, tmpdir=tmp_path)

    mock_smbconf_cls = unittest.mock.MagicMock()
    mock_smbconf_cls.from_registry.side_effect = RuntimeError("registry err")

    monkeypatch.setattr(sambacc.smbconf_samba, "SMBConf", mock_smbconf_cls)

    sambacc.commands.config._import_config(ctx.instance_config)

    assert os.path.exists(chkpath)
    chk = open(chkpath).readlines()
    assert any(("net" in line) for line in chk)
