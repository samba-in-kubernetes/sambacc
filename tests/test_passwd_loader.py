import io

import sambacc.passwd_loader
from .test_config import config2

etc_passwd1 = """
root:x:0:0:root:/root:/bin/bash
bin:x:1:1:bin:/bin:/sbin/nologin
daemon:x:2:2:daemon:/sbin:/sbin/nologin
adm:x:3:4:adm:/var/adm:/sbin/nologin
lp:x:4:7:lp:/var/spool/lpd:/sbin/nologin
sync:x:5:0:sync:/sbin:/bin/sync
shutdown:x:6:0:shutdown:/sbin:/sbin/shutdown
halt:x:7:0:halt:/sbin:/sbin/halt
mail:x:8:12:mail:/var/spool/mail:/sbin/nologin
operator:x:11:0:operator:/root:/sbin/nologin
games:x:12:100:games:/usr/games:/sbin/nologin
ftp:x:14:50:FTP User:/var/ftp:/sbin/nologin
nobody:x:65534:65534:Kernel Overflow User:/:/sbin/nologin
dbus:x:81:81:System message bus:/:/sbin/nologin
""".strip()

etc_group1 = """
root:x:0:
bin:x:1:
daemon:x:2:
sys:x:3:
adm:x:4:
tty:x:5:
disk:x:6:
lp:x:7:
mem:x:8:
kmem:x:9:
wheel:x:10:
cdrom:x:11:
mail:x:12:
man:x:15:
dialout:x:18:
floppy:x:19:
games:x:20:
tape:x:33:
video:x:39:
ftp:x:50:
lock:x:54:
audio:x:63:
users:x:100:
nobody:x:65534:
utmp:x:22:
utempter:x:35:
kvm:x:36:
dbus:x:81:
""".strip()


def test_read_existing_passwd():
    fh = io.StringIO(etc_passwd1)
    pfl = sambacc.passwd_loader.PasswdFileLoader()
    pfl.readfp(fh)
    assert len(pfl.lines) == 14
    assert pfl.lines[0].startswith("root")
    fh2 = io.StringIO()
    pfl.writefp(fh2)
    assert etc_passwd1 == fh2.getvalue()


def test_read_existing_group():
    fh = io.StringIO(etc_group1)
    pfl = sambacc.passwd_loader.GroupFileLoader()
    pfl.readfp(fh)
    assert len(pfl.lines) == 28
    assert pfl.lines[0].startswith("root")
    fh2 = io.StringIO()
    pfl.writefp(fh2)
    assert etc_group1 == fh2.getvalue()


def test_add_user():
    fh = io.StringIO(config2)
    g = sambacc.config.GlobalConfig(fh)
    ic = g.get("foobar")
    users = list(ic.users())

    pfl = sambacc.passwd_loader.PasswdFileLoader()
    for u in users:
        pfl.add_user(u)
    assert len(pfl.lines) == 3
    fh2 = io.StringIO()
    pfl.writefp(fh2)
    txt = fh2.getvalue()
    assert "alice:x:" in txt
    assert "bob:x:" in txt
    assert "carol:x:" in txt


def test_add_group():
    fh = io.StringIO(config2)
    g = sambacc.config.GlobalConfig(fh)
    ic = g.get("foobar")
    groups = list(ic.groups())

    gfl = sambacc.passwd_loader.GroupFileLoader()
    for g in groups:
        gfl.add_group(g)
    # test that duplicates don't add extra lines
    for g in groups:
        gfl.add_group(g)
    assert len(gfl.lines) == 3
    fh2 = io.StringIO()
    gfl.writefp(fh2)
    txt = fh2.getvalue()
    assert "alice:x:" in txt
    assert "bob:x:" in txt
    assert "carol:x:" in txt


def test_read_passwd_file(tmp_path):
    fname = tmp_path / "read_etc_passwd"
    with open(fname, "w") as fh:
        fh.write(etc_passwd1)
    pfl = sambacc.passwd_loader.PasswdFileLoader(fname)
    pfl.read()
    assert len(pfl.lines) == 14
    assert pfl.lines[0].startswith("root")
    fh2 = io.StringIO()
    pfl.writefp(fh2)
    assert etc_passwd1 == fh2.getvalue()


def test_write_passwd_file(tmp_path):
    fh = io.StringIO(config2)
    g = sambacc.config.GlobalConfig(fh)
    ic = g.get("foobar")
    users = list(ic.users())

    fname = tmp_path / "write_etc_passwd"
    with open(fname, "w") as fh:
        fh.write(etc_passwd1)

    pfl = sambacc.passwd_loader.PasswdFileLoader(fname)
    pfl.read()
    for u in users:
        pfl.add_user(u)
    # test that duplicates don't add extra lines
    for u in users:
        pfl.add_user(u)
    assert len(pfl.lines) == 17
    pfl.write()

    with open(fname) as fh:
        txt = fh.read()
    assert "root:x:" in txt
    assert "\nalice:x:" in txt
    assert "\nbob:x:" in txt
    assert "\ncarol:x:" in txt
