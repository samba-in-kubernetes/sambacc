#
# sambacc: a samba container configuration tool
# Copyright (C) 2026  John Mulligan
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
import os

import sambacc.commands.initialize
import sambacc.config

config1 = """
{
  "samba-container-config": "v0",
  "configs": {
    "test": {
      "instance_name": "test",
      "globals": ["default"],
      "shares": ["real", "virt"]
    }
  },
  "globals": {"default": {"options": {"security": "user"}}},
  "shares": {
    "real": {
      "options": {"path": "SHAREROOT/real"}
    },
    "virt": {
      "meta": {"origin": "virtual"},
      "options": {"path": "SHAREROOT/home/%U"}
    }
  }
}
"""


class FakeContext:
    def __init__(self, instance_config):
        self.cli = argparse.Namespace()
        self.instance_config = instance_config
        self.require_validation = False


def _context(tmp_path):
    root = str(tmp_path / "shares")
    cfg_path = str(tmp_path / "config.json")
    with open(cfg_path, "w") as fh:
        fh.write(config1.replace("SHAREROOT", root))
    iconfig = sambacc.config.read_config_files([cfg_path]).get("test")
    return FakeContext(iconfig), root


def test_ensure_share_paths_skips_virtual(tmp_path):
    ctx, root = _context(tmp_path)

    sambacc.commands.initialize.ensure_share_paths(ctx)

    # a share with a real path is created
    assert os.path.isdir(os.path.join(root, "real"))
    # a virtual share's path is left alone: creating it would make a
    # directory literally named "%U", which smbd never uses.
    assert not os.path.exists(os.path.join(root, "home", "%U"))
    assert not os.path.exists(os.path.join(root, "home"))
