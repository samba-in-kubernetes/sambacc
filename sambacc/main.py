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

import argparse
import os
import sys
import time

import sambacc.config as config
import sambacc.join as joinutil
import sambacc.netcmd_loader as nc
import sambacc.nsswitch_loader as nsswitch
import sambacc.passdb_loader as passdb
import sambacc.passwd_loader as ugl
import sambacc.paths as paths
import sambacc.container_dns as container_dns

DEFAULT_CONFIG = "/etc/samba/container/config.json"
DEFAULT_JOIN_MARKER = "/var/lib/samba/container-join-marker.json"
WAIT_SECONDS = 5


class Fail(ValueError):
    pass


def print_config(cli, config):
    cfgs = cli.config or []
    iconfig = config.read_config_files(cfgs).get(cli.identity)
    nc.template_config(sys.stdout, iconfig)


def import_config(cli, config):
    # there are some expectations about what dirs exist and perms
    paths.ensure_samba_dirs()

    cfgs = cli.config or []
    iconfig = config.read_config_files(cfgs).get(cli.identity)
    loader = nc.NetCmdLoader()
    loader.import_config(iconfig)


def import_users(cli, config):
    """Import (locally defined) users and groups into the system
    config files and samba passdb. This enables the configured users
    to log into the smbd instance.
    """
    cfgs = cli.config or []
    iconfig = config.read_config_files(cfgs).get(cli.identity)
    etc_passwd_loader = ugl.PasswdFileLoader(cli.etc_passwd_path)
    etc_group_loader = ugl.GroupFileLoader(cli.etc_group_path)
    smb_passdb_loader = passdb.PassDBLoader()

    etc_passwd_loader.read()
    etc_group_loader.read()
    for u in iconfig.users():
        etc_passwd_loader.add_user(u)
    for g in iconfig.groups():
        etc_group_loader.add_group(g)
    etc_passwd_loader.write()
    etc_group_loader.write()

    for u in iconfig.users():
        smb_passdb_loader.add_user(u)
    return


def init_container(cli, config):
    """Run all of the standard set-up actions."""
    import_config(cli, config)
    import_users(cli, config)

    # should nsswitch validation/edit be conditional only on ads?
    nss = nsswitch.NameServiceSwitchLoader("/etc/nsswitch.conf")
    nss.read()
    if not nss.winbind_enabled():
        nss.ensure_winbind_enabled()
        nss.write()


def run_container(cli, config):
    if not getattr(cli, "no_init", False):
        init_container(cli, config)
    else:
        paths.ensure_samba_dirs()
    if cli.target == "smbd":
        # execute smbd process
        cmd = [
            "/usr/sbin/smbd",
            "--foreground",
            "--log-stdout",
            "--no-process-group",
        ]
        os.execvp(cmd[0], cmd)
    elif cli.target == "winbindd":
        if getattr(cli, "insecure_auto_join", False):
            join(cli, config)
        # execute winbind process
        cmd = [
            "/usr/sbin/winbindd",
            "--foreground",
            "--stdout",
            "--no-process-group",
        ]
        os.execvp(cmd[0], cmd)
    else:
        raise Fail(f"invalid target process: {cli.target}")


def _print_join_error(err):
    print(f"ERROR: {err}", file=sys.stderr)
    for suberr in getattr(err, "errors", []):
        print(f"  - {suberr}", file=sys.stderr)


def _add_join_sources(joiner, cli, config):
    if cli.insecure or getattr(cli, "insecure_auto_join", False):
        upass = joinutil.UserPass(cli.username, cli.password)
        joiner.add_source(joinutil.JoinBy.PASSWORD, upass)
    if cli.files:
        for path in cli.join_files or []:
            joiner.add_source(joinutil.JoinBy.FILE, path)
    if cli.interactive:
        upass = joinutil.UserPass(cli.username)
        joiner.add_source(joinutil.JoinBy.INTERACTIVE, upass)


def join(cli, config):
    """Perform a domain join.
    The cli supports specificying different methods from which
    data needed to perform the join will be sourced.
    """
    # maybe in the future we'll have more secure methods
    joiner = joinutil.Joiner(cli.join_marker)
    _add_join_sources(joiner, cli, config)
    try:
        joiner.join()
    except joinutil.JoinError as err:
        _print_join_error(err)
        raise Fail("failed to join to a domain")


def must_join(cli, config):
    """Perform a domain join if possible, otherwise wait or fail.
    If waiting is enabled the marker file is polled.
    """
    joiner = joinutil.Joiner(cli.join_marker)
    if joiner.did_join():
        print("already joined")
        return
    # Interactive join is not allowed on must-join
    setattr(cli, "interactive", False)
    _add_join_sources(joiner, cli, config)
    try:
        joiner.join()
    except joinutil.JoinError as err:
        _print_join_error(err)
    if not cli.wait:
        raise Fail(
            "failed to join to a domain and waiting for join is disabled"
        )
    while True:
        if joiner.did_join():
            print("found valid join marker")
            return
        time.sleep(WAIT_SECONDS)


def check(cli, config):
    """Check a given subsystem is functioning."""
    if cli.target == "winbind":
        cmd = [
            "wbinfo",
            "--ping",
        ]
        os.execvp(cmd[0], cmd)
    else:
        raise Fail("unknown subsystem: {}".format(cli.target))


def dns_register(cli, config):
    """Register DNS entries with AD based on JSON state file.
    This file is expected to be supplied & kept up to date by
    a container-orchestration specific component.
    """
    cfgs = cli.config or []
    iconfig = config.read_config_files(cfgs).get(cli.identity)
    if cli.domain:
        domain = cli.domain
    else:
        try:
            domain = dict(iconfig.global_options())["realm"].lower()
        except KeyError:
            raise Fail("instance not configured with domain (realm)")
    try:
        waiter = container_dns.INotify(cli.source, print_func=print)
    except ValueError:
        print("disabling inotify support")
        waiter = container_dns.Sleeper()
    if cli.watch:
        container_dns.watch(
            domain,
            cli.source,
            container_dns.parse_and_update,
            waiter.wait,
            print_func=print,
        )
    else:
        container_dns.parse_and_update(domain, cli.source)


default_cfunc = print_config


def from_env(ns, var, ename, default=None, vtype=str):
    value = getattr(ns, var, None)
    if not value:
        value = os.environ.get(ename, "")
    if vtype is not None:
        value = vtype(value)
    if value:
        setattr(ns, var, value)


def split_paths(value):
    if not value:
        return value
    if not isinstance(value, list):
        value = [value]
    out = []
    for v in value:
        for part in v.split(":"):
            out.append(part)
    return out


def _toggle_option(parser, arg, dest, helpfmt):
    parser.add_argument(
        arg,
        action="store_true",
        dest=dest,
        help=helpfmt.format("Enable"),
    )
    negarg = arg.replace("--", "--no-")
    parser.add_argument(
        negarg,
        action="store_false",
        dest=dest,
        help=helpfmt.format("Disable"),
    )
    return parser


def pre_action(cli):
    """Handle debugging/diagnostic related options before the target
    action of the command is performed.
    """
    if cli.debug_delay:
        time.sleep(int(cli.debug_delay))


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        action="append",
        help=(
            "Specify source configuration"
            " (can also be set in the environment by SAMBACC_CONFIG)."
        ),
    )
    parser.add_argument(
        "--identity",
        help=(
            "A string identifying the local identity"
            " (can also be set in the environment by SAMBA_CONTAINER_ID)."
        ),
    )
    parser.add_argument(
        "--etc-passwd-path",
        default="/etc/passwd",
        help="Specify a path for the passwd file.",
    )
    parser.add_argument(
        "--etc-group-path",
        default="/etc/group",
        help="Specify a path for the group file.",
    )
    parser.add_argument(
        "--username",
        default="Administrator",
        help="Specify a user name for domain access.",
    )
    parser.add_argument(
        "--password", default="", help="Specify a password for domain access."
    )
    parser.add_argument(
        "--debug-delay",
        type=int,
        help="Delay activity for a specified number of seconds.",
    )
    parser.add_argument(
        "--join-marker",
        default=DEFAULT_JOIN_MARKER,
        help="Path to a file used to indicate a join has been peformed.",
    )
    sub = parser.add_subparsers()
    p_print_config = sub.add_parser(
        "print-config",
        help=(
            "Display the samba configuration sourced from the sambacc config"
            " in the format of smb.conf."
        ),
    )
    p_print_config.set_defaults(cfunc=print_config)
    p_import = sub.add_parser(
        "import",
        help=(
            "Import configuration parameters from the sambacc config to"
            " samba's registry config."
        ),
    )
    p_import.set_defaults(cfunc=import_config)
    p_import_users = sub.add_parser(
        "import-users",
        help=(
            "Import users and groups from the sambacc config to the passwd"
            " and group files to support local (non-domain based) login."
        ),
    )
    p_import_users.set_defaults(cfunc=import_users)
    p_init = sub.add_parser(
        "init", help=("Initialize the entire container environment.")
    )
    p_init.set_defaults(cfunc=init_container)
    p_run = sub.add_parser("run", help=("Run a specified server process."))
    p_run.set_defaults(cfunc=run_container)
    p_run.add_argument(
        "--no-init",
        action="store_true",
        help=(
            "Do not initialize the container envionment."
            " Only start running the target process."
        ),
    )
    p_run.add_argument(
        "--insecure-auto-join",
        action="store_true",
        help=(
            "Perform an inscure domain join prior to starting a service."
            " Based on env vars JOIN_USERNAME and INSECURE_JOIN_PASSWORD."
        ),
    )
    p_run.add_argument(
        "target", choices=["smbd", "winbindd"], help="Which process to run"
    )
    p_join = sub.add_parser(
        "join",
        help=(
            "Perform a domain join. The supported sources for join"
            " can be provided by supplying command line arguments."
            " This includes an *insecure* mode that sources the password"
            " from the CLI or environment. Use this only on"
            " testing/non-production purposes."
        ),
    )
    p_join.set_defaults(
        cfunc=join, insecure=False, files=True, interactive=True
    )
    _toggle_option(
        p_join,
        arg="--insecure",
        dest="insecure",
        helpfmt="{} taking user/password from CLI or environment.",
    )
    _toggle_option(
        p_join,
        arg="--files",
        dest="files",
        helpfmt="{} reading user/password from JSON files.",
    )
    _toggle_option(
        p_join,
        arg="--interactive",
        dest="interactive",
        helpfmt="{} interactive password prompt.",
    )
    p_join.add_argument(
        "--join-file",
        "-j",
        dest="join_files",
        action="append",
        help="Path to file with user/password in JSON format.",
    )
    p_must_join = sub.add_parser(
        "must-join",
        help=(
            "If possible, perform an unattended domain join. Otherwise,"
            " exit or block until a join has been perfmed by another process."
        ),
    )
    p_must_join.set_defaults(
        cfunc=must_join, insecure=False, files=True, wait=True
    )
    _toggle_option(
        p_must_join,
        arg="--insecure",
        dest="insecure",
        helpfmt="{} taking user/password from CLI or environment.",
    )
    _toggle_option(
        p_must_join,
        arg="--files",
        dest="files",
        helpfmt="{} reading user/password from JSON files.",
    )
    _toggle_option(
        p_must_join,
        arg="--wait",
        dest="wait",
        helpfmt="{} waiting until a join is done.",
    )
    p_must_join.add_argument(
        "--join-file",
        "-j",
        dest="join_files",
        action="append",
        help="Path to file with user/password in JSON format.",
    )
    p_check = sub.add_parser(
        "check",
        help=("Check that a given subsystem is functioning."),
    )
    p_check.set_defaults(cfunc=check)
    p_check.add_argument(
        "target",
        choices=["winbind"],
        help="Name of the target subsystem to check.",
    )
    p_dns_reg = sub.add_parser(
        "dns-register",
        help=("Register container IP(s) with AD DNS."),
    )
    p_dns_reg.set_defaults(cfunc=dns_register)
    p_dns_reg.add_argument(
        "--watch",
        action="store_true",
        help=("If set, watch the source for changes and update DNS."),
    )
    p_dns_reg.add_argument(
        "--domain",
        default="",
        help=("Manually specify parent domain for DNS entries."),
    )
    p_dns_reg.add_argument("source", help="Path to source JSON file.")

    cli = parser.parse_args(args)
    from_env(
        cli,
        "config",
        "SAMBACC_CONFIG",
        vtype=split_paths,
        default=DEFAULT_CONFIG,
    )
    from_env(
        cli,
        "join_files",
        "SAMBACC_JOIN_FILES",
        vtype=split_paths,
    )
    from_env(cli, "identity", "SAMBA_CONTAINER_ID")
    from_env(cli, "username", "JOIN_USERNAME")
    from_env(cli, "password", "INSECURE_JOIN_PASSWORD")

    if not cli.identity:
        raise Fail("missing container identity")

    pre_action(cli)
    cfunc = getattr(cli, "cfunc", default_cfunc)
    cfunc(cli, config)

    return


if __name__ == "__main__":
    main()
