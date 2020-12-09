# sambacc: Samba Container Configurator

import argparse
import os
import sys

import sambacc.config as config
import sambacc.netcmd_loader as nc

DEFAULT_CONFIG = "/etc/samba/container/config.json"


class Fail(ValueError):
    pass


def print_config(cli, config):
    iconfig = config.read_config(cli.config).get(cli.identity)
    nc.template_config(sys.stdout, iconfig)


def import_config(cli, config):
    iconfig = config.read_config(cli.config).get(cli.identity)
    loader = nc.NetCmdLoader()
    loader.import_config(iconfig)


default_cfunc = print_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--identity")
    sub = parser.add_subparsers()
    p_print_config = sub.add_parser("print-config")
    p_print_config.set_defaults(cfunc=print_config)
    p_import = sub.add_parser("import")
    p_import.set_defaults(cfunc=import_config)
    cli = parser.parse_args()

    if not cli.identity:
        cli.identity = os.environ.get("SAMBA_CONTAINER_ID")
        if not cli.identity:
            raise Fail("missing container identity")

    cfunc = getattr(cli, "cfunc", default_cfunc)
    cfunc(cli, config)

    return


if __name__ == "__main__":
    main()
