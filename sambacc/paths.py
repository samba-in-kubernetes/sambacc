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

import errno
import os


def ensure_samba_dirs(root: str = "/") -> None:
    """Ensure that certain directories that samba servers expect will
    exist. This is useful when mapping iniitally empty dirs into
    the container.
    """
    smb_dir = os.path.join(root, "var/lib/samba")
    smb_private_dir = os.path.join(smb_dir, "private")
    smb_run_dir = os.path.join(root, "run/samba")
    wb_sockets_dir = os.path.join(smb_run_dir, "winbindd")

    _mkdir(smb_dir)
    _mkdir(smb_private_dir)

    _mkdir(smb_run_dir)
    _mkdir(wb_sockets_dir)
    os.chmod(wb_sockets_dir, 0o755)


def _mkdir(path: str) -> None:
    try:
        os.mkdir(path)
    except OSError as err:
        if getattr(err, "errno", 0) != errno.EEXIST:
            raise


def ensure_share_dirs(path: str, root: str = "/") -> None:
    """Ensure that the given path exists.
    The optional root argument allows "reparenting" the path
    into a virtual root dir.
    """
    while path.startswith("/"):
        path = path[1:]
    path = os.path.join(root, path)
    os.makedirs(path, exist_ok=True)
