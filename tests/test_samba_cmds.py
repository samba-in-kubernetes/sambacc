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

import sambacc.samba_cmds


def test_create_samba_command():
    cmd = sambacc.samba_cmds.SambaCommand("hello")
    assert cmd.name == "hello"
    cmd2 = cmd["world"]
    assert cmd.name == "hello"
    assert list(cmd) == ["hello"]
    assert list(cmd2) == ["hello", "world"]


def test_debug_command():
    cmd = sambacc.samba_cmds.SambaCommand("beep", debug="5")
    assert list(cmd) == ["beep", "--debuglevel=5"]


def test_global_debug():
    sambacc.samba_cmds.set_global_debug("7")
    try:
        cmd = sambacc.samba_cmds.SambaCommand("cheep")
        assert list(cmd) == ["cheep", "--debuglevel=7"]
    finally:
        sambacc.samba_cmds.set_global_debug("")


def test_global_prefix():
    # enabled
    sambacc.samba_cmds.set_global_prefix(["bob"])
    try:
        cmd = sambacc.samba_cmds.SambaCommand("deep")
        assert list(cmd) == ["bob", "deep"]
        assert cmd.name == "bob"
    finally:
        sambacc.samba_cmds.set_global_prefix([])

    # disabled
    cmd = sambacc.samba_cmds.SambaCommand("deep")
    assert list(cmd) == ["deep"]
    assert cmd.name == "deep"


def test_global_prefix_extended():
    # enabled
    sambacc.samba_cmds.set_global_prefix(["frank"])
    try:
        cmd = sambacc.samba_cmds.SambaCommand("deep")[
            "13", "--future=not-too-distant"
        ]
        assert list(cmd) == ["frank", "deep", "13", "--future=not-too-distant"]
        assert cmd.name == "frank"
    finally:
        sambacc.samba_cmds.set_global_prefix([])

    # disabled, must not "inherit" the prefix
    cmd2 = cmd["--scheme", "evil"]
    assert list(cmd2) == [
        "deep",
        "13",
        "--future=not-too-distant",
        "--scheme",
        "evil",
    ]
    assert cmd2.name == "deep"


def test_command_repr():
    cmd = sambacc.samba_cmds.SambaCommand("doop")
    cr = repr(cmd)
    assert cr.startswith("SambaCommand")
    assert "doop" in cr


def test_encode_none():
    res = sambacc.samba_cmds.encode(None)
    assert res == b""


def test_execute():
    import os

    cmd = sambacc.samba_cmds.SambaCommand("true")
    pid = os.fork()
    if pid == 0:
        sambacc.samba_cmds.execute(cmd)
    else:
        _, status = os.waitpid(pid, 0)
        assert status == 0


def test_create_command_args():
    # this is the simpler base class for SambaCommand. It lacks
    # the samba debug level option.
    cmd = sambacc.samba_cmds.CommandArgs("something")
    assert cmd.name == "something"
    cmd2 = cmd["nice"]
    assert cmd.name == "something"
    assert list(cmd) == ["something"]
    assert list(cmd2) == ["something", "nice"]


def test_command_args_repr():
    r = str(sambacc.samba_cmds.CommandArgs("something", ["nice"]))
    assert r.startswith("CommandArgs")
    assert "something" in r
    assert "nice" in r


def test_get_samba_specifics(monkeypatch):
    monkeypatch.setenv("SAMBA_SPECIFICS", "")
    ss = sambacc.samba_cmds.get_samba_specifics()
    assert not ss

    monkeypatch.setenv("SAMBA_SPECIFICS", "wibble,quux")
    ss = sambacc.samba_cmds.get_samba_specifics()
    assert ss
    assert len(ss) == 2
    assert "wibble" in ss
    assert "quux" in ss


def test_smbd_foreground(monkeypatch):
    monkeypatch.setenv("SAMBA_SPECIFICS", "")
    sf = sambacc.samba_cmds.smbd_foreground()
    assert "smbd" in sf.name
    assert "--log-stdout" in sf.argv()
    assert "--debug-stdout" not in sf.argv()

    monkeypatch.setenv("SAMBA_SPECIFICS", "daemon_cli_debug_output")
    sf = sambacc.samba_cmds.smbd_foreground()
    assert "smbd" in sf.name
    assert "--log-stdout" not in sf.argv()
    assert "--debug-stdout" in sf.argv()


def test_winbindd_foreground(monkeypatch):
    monkeypatch.setenv("SAMBA_SPECIFICS", "")
    wf = sambacc.samba_cmds.winbindd_foreground()
    assert "winbindd" in wf.name
    assert "--stdout" in wf.argv()
    assert "--debug-stdout" not in wf.argv()

    monkeypatch.setenv("SAMBA_SPECIFICS", "daemon_cli_debug_output")
    wf = sambacc.samba_cmds.winbindd_foreground()
    assert "winbindd" in wf.name
    assert "--stdout" not in wf.argv()
    assert "--debug-stdout" in wf.argv()
