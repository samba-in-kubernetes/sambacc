import contextlib
import io
import os
import pytest
import shutil

import sambacc.passdb_loader
import sambacc.config
from .test_config import config2

_smb_conf = """
[global]
cache directory = {path}
state directory = {path}
private dir = {path}
include = registry
"""

passwd_append1 = [
    "alice:x:1010:1010:ALICE:/home/alice:/bin/bash\n",
    "bob:x:1011:1011:BOB:/home/bob:/bin/bash\n",
    "carol:x:1010:1010:carol:/home/alice:/bin/bash\n",
]


@pytest.fixture(scope="function")
def smb_conf(tmp_path):
    data_path = tmp_path / "_samba"
    data_path.mkdir()
    smb_conf_path = tmp_path / "smb.conf"
    with open(smb_conf_path, "w") as fh:
        fh.write(_smb_conf.format(path=data_path))
    return smb_conf_path


@contextlib.contextmanager
def alter_passwd(path, append):
    bkup = path / "passwd.bak"
    mypasswd = os.environ.get("NSS_WRAPPER_PASSWD")
    shutil.copy(mypasswd, bkup)
    with open(mypasswd, "a") as fh:
        fh.write("\n")
        for line in passwd_append1:
            fh.write(line)
    yield
    shutil.copy(bkup, mypasswd)


def requires_passdb_modules():
    try:
        sambacc.passdb_loader._samba_modules()
    except ImportError:
        pytest.skip("unable to load samba passdb modules")


def test_init_custom_smb_conf(smb_conf):
    requires_passdb_modules()
    sambacc.passdb_loader.PassDBLoader(smbconf=str(smb_conf))


def test_init_default_smb_conf():
    requires_passdb_modules()
    # this is a bit hacky, but I don't want to assume the local
    # system has or doesn't have a "real" smb.conf
    if os.path.exists("/etc/samba/smb.conf"):
        sambacc.passdb_loader.PassDBLoader(smbconf=None)
    else:
        with pytest.raises(Exception):
            sambacc.passdb_loader.PassDBLoader(smbconf=None)


def test_add_users(tmp_path, smb_conf):
    requires_passdb_modules()
    # TODO: actually use nss_wrapper!
    if not os.environ.get("NSS_WRAPPER_PASSWD"):
        pytest.skip("need to have path to passwd file")
    if os.environ.get("WRITABLE_PASSWD") != "yes":
        pytest.skip("need to append users to passwd file")
    with alter_passwd(tmp_path, passwd_append1):
        fh = io.StringIO(config2)
        g = sambacc.config.GlobalConfig(fh)
        ic = g.get("foobar")
        users = list(ic.users())

        pdbl = sambacc.passdb_loader.PassDBLoader(smbconf=str(smb_conf))
        for u in users:
            pdbl.add_user(u)


def test_add_user_not_in_passwd(smb_conf):
    requires_passdb_modules()
    pdbl = sambacc.passdb_loader.PassDBLoader(smbconf=str(smb_conf))

    # Irritatingly, the passwd file contents appear to be cached
    # so we need to make up a user that is def. not in the etc passwd
    # equivalent, in order to get samba libs to reject it
    urec = dict(name="nogoodnik", uid=101010, gid=101010, password="yuck")
    ubad = sambacc.config.UserEntry(None, urec, 0)
    with pytest.raises(Exception):
        pdbl.add_user(ubad)


def test_add_user_no_passwd(smb_conf):
    requires_passdb_modules()
    pdbl = sambacc.passdb_loader.PassDBLoader(smbconf=str(smb_conf))

    # Irritatingly, the passwd file contents appear to be cached
    # so we need to make up a user that is def. not in the etc passwd
    # equivalent, in order to get samba libs to reject it
    urec = dict(name="bob", uid=1011, gid=1011)
    ubad = sambacc.config.UserEntry(None, urec, 0)
    with pytest.raises(ValueError):
        pdbl.add_user(ubad)
