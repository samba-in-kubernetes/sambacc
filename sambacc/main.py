# sambacc: Samba Container Configurator

import argparse
import os
import sys

import sambacc.config as config
import sambacc.netcmd_loader as nc
import sambacc.passwd_loader as ugl
import sambacc.passdb_loader as passdb

DEFAULT_CONFIG = "/etc/samba/container/config.json"


class Fail(ValueError):
    pass


def print_config(cli, config):
    iconfig = config.read_config_files(cli.config).get(cli.identity)
    nc.template_config(sys.stdout, iconfig)


def import_config(cli, config):
    iconfig = config.read_config_files(cli.config).get(cli.identity)
    loader = nc.NetCmdLoader()
    loader.import_config(iconfig)


def import_users(cli, config):
    """Import (locally defined) users and groups into the system
    config files and samba passdb. This enables the configured users
    to log into the smbd instance.
    """
    iconfig = config.read_config_files(cli.config).get(cli.identity)
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
    """Run all of the standard set-up actions.
    """
    import_config(cli, config)
    import_users(cli, config)


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
    return value


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        action="append",
        help="Specify source configuration (or env var SAMBACC_CONFIG)",
    )
    parser.add_argument(
        "--identity",
        help=(
            "A string identifying the local identity"
            " (or env var SAMBA_CONTAINER_ID"
        ),
    )
    parser.add_argument(
        "--etc-passwd-path", default="/etc/passwd",
    )
    parser.add_argument(
        "--etc-group-path", default="/etc/group",
    )
    sub = parser.add_subparsers()
    p_print_config = sub.add_parser("print-config")
    p_print_config.set_defaults(cfunc=print_config)
    p_import = sub.add_parser("import")
    p_import.set_defaults(cfunc=import_config)
    p_import_users = sub.add_parser("import-users")
    p_import_users.set_defaults(cfunc=import_users)
    p_init = sub.add_parser("init")
    p_init.set_defaults(cfunc=init_container)
    cli = parser.parse_args(args)
    from_env(
        cli,
        "config",
        "SAMBACC_CONFIG",
        vtype=split_paths,
        default=DEFAULT_CONFIG,
    )
    from_env(cli, "identity", "SAMBA_CONTAINER_ID")

    if not cli.identity:
        raise Fail("missing container identity")

    cfunc = getattr(cli, "cfunc", default_cfunc)
    cfunc(cli, config)

    return


if __name__ == "__main__":
    main()
