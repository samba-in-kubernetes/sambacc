import pytest

import sambacc.main
from .test_netcmd_loader import config1


def run(*args):
    return sambacc.main.main(args)


def test_no_id(capsys):
    with pytest.raises(sambacc.main.Fail):
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
