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

import pytest

import sambacc.commands.cli
import sambacc.commands.main
from .test_netcmd_loader import config1


def run(*args):
    return sambacc.commands.main.main(args)


def test_no_id(capsys):
    with pytest.raises(sambacc.commands.cli.Fail):
        run("print-config")


def test_print_config(capsys, tmp_path):
    fname = tmp_path / "sample.json"
    with open(fname, "w") as fh:
        fh.write(config1)
    run("--identity", "foobar", "--config", str(fname), "print-config")
    out, err = capsys.readouterr()
    assert "[global]" in out
    assert "netbios name = GANDOLPH" in out
    assert "[share]" in out
    assert "path = /share" in out
    assert "[stuff]" in out
    assert "path = /mnt/stuff" in out


def test_print_config_env_vars(capsys, tmp_path, monkeypatch):
    fname = tmp_path / "sample.json"
    with open(fname, "w") as fh:
        fh.write(config1)
    monkeypatch.setenv("SAMBACC_CONFIG", str(fname))
    monkeypatch.setenv("SAMBA_CONTAINER_ID", "foobar")
    run("print-config")
    out, err = capsys.readouterr()
    assert "[global]" in out
    assert "netbios name = GANDOLPH" in out
    assert "[share]" in out
    assert "path = /share" in out
    assert "[stuff]" in out
    assert "path = /mnt/stuff" in out
