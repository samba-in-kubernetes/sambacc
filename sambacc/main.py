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


def from_env(varname, default=None, help=None):
    def _convert(v):
        if not v:
            v = os.environ.get(varname, "")
        if not v and default is not None:
            v = default
        return str(v)

    if help:
        chelp = f"{help} (equivalent to setting {varname})"
    else:
        chelp = None
    return {
        "type": _convert,
        "default": "",
        "help": chelp,
    }


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        **from_env(
            "SAMBACC_CONFIG",
            default=DEFAULT_CONFIG,
            help="Specify source configuration",
        ),
    )
    parser.add_argument(
        "--identity",
        **from_env(
            "SAMBA_CONTAINER_ID",
            help="A string identifying the local idententy",
        ),
    )
    sub = parser.add_subparsers()
    p_print_config = sub.add_parser("print-config")
    p_print_config.set_defaults(cfunc=print_config)
    p_import = sub.add_parser("import")
    p_import.set_defaults(cfunc=import_config)
    cli = parser.parse_args(args)

    if not cli.identity:
        raise Fail("missing container identity")

    cfunc = getattr(cli, "cfunc", default_cfunc)
    cfunc(cli, config)

    return


if __name__ == "__main__":
    main()
