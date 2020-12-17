import json

_VALID_VERSIONS = ["v0"]


def read_config(fname):
    """Deprecated. Remove."""
    return read_config_files([fname])


def read_config_files(fnames):
    """Read the global container config from the given filenames.
    """
    gconfig = GlobalConfig()
    for fname in fnames:
        with open(fname) as fh:
            gconfig.load(fh)
    return gconfig


class GlobalConfig:
    def __init__(self, source=None):
        self.data = {}
        if source is not None:
            self.load(source)

    def load(self, source):
        data = json.load(source)
        # short-cut to validate that this is something we want to consume
        version = data.get("samba-container-config")
        if version is None:
            raise ValueError("Invalid config: no samba-container-config key")
        elif version not in _VALID_VERSIONS:
            raise ValueError(f"Invalid config: unknown version {version}")
        self.data.update(data)

    def get(self, ident):
        iconfig = self.data["configs"][ident]
        return InstanceConfig(self, iconfig)


class InstanceConfig:
    def __init__(self, conf, iconfig):
        self.gconfig = conf
        self.iconfig = iconfig

    def global_options(self):
        """Iterate over global options."""
        # Pull in all global sections that apply
        gnames = self.iconfig["globals"]
        for gname in gnames:
            global_section = self.gconfig.data["globals"][gname]
            for k, v in global_section.get("options", {}).items():
                yield k, v
        # Special, per-instance settings
        instance_name = self.iconfig.get("instance_name", None)
        if instance_name:
            yield "netbios name", instance_name

    def shares(self):
        """Iterate over share configs."""
        for sname in self.iconfig.get("shares", []):
            yield ShareConfig(self.gconfig, sname)


class ShareConfig:
    def __init__(self, conf, sharename):
        self.gconfig = conf
        self.name = sharename

    def share_options(self):
        """Iterate over share options."""
        share_section = self.gconfig.data["shares"][self.name]
        return iter(share_section.get("options", {}).items())
