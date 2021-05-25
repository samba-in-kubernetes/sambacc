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

import sys

import sambacc.netcmd_loader as nc
import sambacc.paths as paths

from .cli import commands


@commands.command(name="print-config")
def print_config(cli, config) -> None:
    """Display the samba configuration sourced from the sambacc config
    in the format of smb.conf.
    """
    cfgs = cli.config or []
    iconfig = config.read_config_files(cfgs).get(cli.identity)
    nc.template_config(sys.stdout, iconfig)


@commands.command(name="import")
def import_config(cli, config) -> None:
    """Import configuration parameters from the sambacc config to
    samba's registry config.
    """
    # there are some expectations about what dirs exist and perms
    paths.ensure_samba_dirs()

    cfgs = cli.config or []
    iconfig = config.read_config_files(cfgs).get(cli.identity)
    loader = nc.NetCmdLoader()
    loader.import_config(iconfig)
