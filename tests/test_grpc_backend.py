#
# sambacc: a samba container configuration tool
# Copyright (C) 2025  John Mulligan
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

import pytest

import sambacc.grpc.backend


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

json1 = """
{
  "timestamp": "2025-05-08T20:41:57.273489+0000",
  "version": "4.23.0pre1-UNKNOWN",
  "smb_conf": "/etc/samba/smb.conf",
  "sessions": {
    "2891148582": {
      "session_id": "2891148582",
      "server_id": {
        "pid": "1243",
        "task_id": "0",
        "vnn": "2",
        "unique_id": "1518712196307698939"
      },
      "uid": 103107,
      "gid": 102513,
      "username": "DOMAIN1\\\\bwayne",
      "groupname": "DOMAIN1\\\\domain users",
      "creation_time": "2025-05-08T20:39:36.456835+00:00",
      "expiration_time": "30828-09-14T02:48:05.477581+00:00",
      "auth_time": "2025-05-08T20:39:36.457633+00:00",
      "remote_machine": "127.0.0.1",
      "hostname": "ipv4:127.0.0.1:59396",
      "session_dialect": "SMB3_11",
      "client_guid": "adc145fe-0677-4ab6-9d61-c25b30211174",
      "encryption": {
        "cipher": "-",
        "degree": "none"
      },
      "signing": {
        "cipher": "AES-128-GMAC",
        "degree": "partial"
      },
      "channels": {
        "1": {
          "channel_id": "1",
          "creation_time": "2025-05-08T20:39:36.456835+00:00",
          "local_address": "ipv4:127.0.0.1:445",
          "remote_address": "ipv4:127.0.0.1:59396",
          "transport": "tcp"
        }
      }
    }
  },
  "tcons": {
    "3757739897": {
      "service": "cephomatic",
      "server_id": {
        "pid": "1243",
        "task_id": "0",
        "vnn": "2",
        "unique_id": "1518712196307698939"
      },
      "tcon_id": "3757739897",
      "session_id": "2891148582",
      "machine": "127.0.0.1",
      "connected_at": "2025-05-08T20:39:36.464088+00:00",
      "encryption": {
        "cipher": "-",
        "degree": "none"
      },
      "signing": {
        "cipher": "-",
        "degree": "none"
      }
    }
  },
  "open_files": {}
}
"""


def _status_json1_check(status):
    assert status.timestamp == "2025-05-08T20:41:57.273489+0000"
    assert len(status.sessions) == 1
    s1 = status.sessions[0]
    assert s1.session_id == "2891148582"
    assert s1.username == "DOMAIN1\\bwayne"
    assert s1.groupname == "DOMAIN1\\domain users"
    assert s1.remote_machine == "127.0.0.1"
    assert s1.hostname == "ipv4:127.0.0.1:59396"
    assert s1.session_dialect == "SMB3_11"
    assert s1.uid == 103107
    assert s1.gid == 102513
    assert len(status.tcons) == 1
    assert s1.encryption
    assert s1.encryption.cipher == ""
    assert s1.encryption.degree == "none"
    assert s1.signing
    assert s1.signing.cipher == "AES-128-GMAC"
    assert s1.signing.degree == "partial"
    t1 = status.tcons[0]
    assert t1.tcon_id == "3757739897"
    assert t1.session_id == "2891148582"
    assert t1.service_name == "cephomatic"


def _fake_command(tmp_path, monkeypatch, *, output="", exitcode=0):
    fakedir = tmp_path / "fake"
    fake = fakedir / "fake.sh"
    outfile = fakedir / "stdout"

    print(fakedir)
    print(fakedir.mkdir, fakedir.mkdir.__doc__)
    fakedir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sambacc.samba_cmds, "_GLOBAL_PREFIX", [str(fake)])

    if output:
        outfile.write_text(output)
    fake.write_text(
        "#!/bin/sh\n"
        f"test -f {outfile} && cat {outfile}\n"
        f"exit {exitcode}\n"
    )
    os.chmod(fake, 0o755)


def _instance_config():
    fh = io.StringIO(config1)
    g = sambacc.config.GlobalConfig(fh)
    return g.get("foobar")


def test_parse_status():
    status = sambacc.grpc.backend.Status.parse(json1)
    _status_json1_check(status)


def test_backend_versions(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch, output="Version 4.99.99\n")
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    v = backend.get_versions()
    assert v.samba_version == "Version 4.99.99"


def test_backend_is_clustered(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch)
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    assert not backend.is_clustered()


def test_backend_status(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch, output=json1)
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    status = backend.get_status()
    _status_json1_check(status)


def test_backend_status_error(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch, exitcode=2)
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    with pytest.raises(Exception):
        backend.get_status()


def test_backend_close_share(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch)
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    backend.close_share("share", denied_users=False)


def test_backend_close_share_error(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch, exitcode=2)
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    with pytest.raises(Exception):
        backend.close_share("share", denied_users=False)


def test_backend_kill_client(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch)
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    backend.kill_client("127.0.0.1")


def test_backend_kill_client_error(tmp_path, monkeypatch):
    _fake_command(tmp_path, monkeypatch, exitcode=2)
    backend = sambacc.grpc.backend.ControlBackend(_instance_config())
    with pytest.raises(Exception):
        backend.kill_client("127.0.0.1")
