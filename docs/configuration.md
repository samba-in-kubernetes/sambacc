
# JSON Configuration Format

Much of the behavior of sambacc is driven by the
configuration files. The following is a high level example of the JSON
structure and a description of these sections.

If sambacc is installed with the `yaml` extra it can support [YAML](#yaml)
based configuration files. If sambacc is installed with the `toml` extra it can
support [TOML](#toml) based configuration files. The JSON support is the
default and is always present.

```json
{
    "samba-container-config": "v0",
    "configs": {
        "config1": {
            "instance_name": "SAMBA",
            "instance_features": [],
            "shares": [
                "testshare"
            ],
            "globals": [
                "default"
            ]
        },
        "config2": {
            "instance_name": "MYDC1",
            "instance_features": [
                "addc"
            ],
            "domain_settings": "testdom"
        }
    },
    "shares": {
        "share": {
            "options": {
                "path": "/share",
                "valid users": "sambauser, otheruser"
            }
        },
        "share2": {
            "options": {
                "path": "/srv/data",
                "valid users": "sambauser, otheruser"
            },
            "permissions": {
                "method": "initialize-share-perms",
                "status_xattr": "user.share-perms-status",
                "mode": "0755"
            }
        }
    },
    "globals": {
        "default": {
            "options": {
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
    "users": {
        "all_entries": [
            {
                "name": "sambauser",
                "password": "samba"
            },
            {
                "name": "bob",
                "uid": 2000,
                "gid": 2000,
                "password": "notSoSafe"
            },
            {
                "name": "alice",
                "uid": 2001,
                "gid": 2001,
                "nt_hash": "B784E584D34839235F6D88A5382C3821"
            }
        ]
    },
    "groups": {
        "all_entries": [
            {
                "name": "bob",
                "gid": 2000
            },
            {
                "name": "alice",
                "gid": 2001
            }
        ]
    },
    "domain_settings": {
        "testdom": {
            "realm": "DIMENSIONX.FOO.TEST",
            "short_domain": "DIMENSIONX",
            "admin_password": "Passw0rd"
        }
    },
    "domain_groups": {
        "testdom": [
            {
                "name": "friends"
            },
            {
                "name": "developers"
            }
        ]
    },
    "domain_users": {
        "testdom": [
            {
                "name": "jfoo",
                "password": "testing0nly.",
                "given_name": "Joe",
                "surname": "Foo",
                "member_of": [
                    "friends",
                    "developers"
                ]
            },
            {
                "name": "qbert",
                "password": "404knot-found",
                "given_name": "Quentin",
                "surname": "Bert",
                "member_of": [
                    "friends"
                ]
            }
        ]
    }
}
```
<!-- fellow vimmers:
    pipe above section `'<,'>!python -m json.tool` to keep neat -->

## The samba-container-config key

Every valid sambacc JSON configuration file contains the key
`samba-container-config` with a value in the form of a string vN were
N is the numeric version number. Currently, only "v0" exists.
This key-value combination allows us to support backwards-incompatible
configuration file format changes in the future.

## Configs Section

The `configs` section is a mapping of configuration names to top-level
configurations. A useable configuration file must have at least one
configuration, but more than one is supported.

Each configuration section is as follows:
* `instance_name` - String. A name for the configuration instance. Used for
  Samba's server (netbios) name. Valid for all configurations.
* `instance_features` - List of strings. Feature flags that alter the
  high level behavior of sambacc. Valid feature flags are: `CTDB`, `ADDC`.
* `shares` - List of strings. The names of one or more share config sections to
  include as part of the sambacc configuration. Valid only for file-server
  configurations (not supported for AD DC).
* `globals` - List of strings. The names of one or more global config sections
  to include as part of the sambacc configuration. Valid for all
  configurations.
* `domain_settings` - String. Name of the AD DC domain configuration. Required
  for AD DC configurations, invalid for all others.

The subsections under `configs` can be used to uniquely identify one server
"instance". Because those server instances may repeat the shares and samba
globals are defined in their own sections and then included in an
instance by referring to them in the `shares` and `globals` section
of these subsections.


## Shares Section

The `shares` section is a mapping of share names to a share-configuration block.
It is assumed that a configuration will have at least one share.

Each share configuration section is as follows:
* `options` - Mapping. The keys and values contained within are processed by
  sambacc and become part of the smb.conf (or functional equivalent)
  when running a Samba server.
* `permissions` - Permissions configuration section:
  * `method` - Permissions method. Known methods are:
    * `none` - Perform no permissions management
    * `initialize-share-perms` - Set share permissions only once. Track status in xattr.
    * `always-share-perms` - Always set share permissions.
  * `status_xattr` - Name of xattr to store status.
  * Remaining key-value pairs are method specific. Unknown keys are ignored.
  * `mode` - String that converts to octal. Unix permissions to set (`initialize-share-perms`, `always-share-perms`).


## Globals Section

The `globals` section is a mapping of named global configs to a
globals-configuration block. It is assumed that a configuration will have
at least one globals section.

Each globals configuration section is as follows:
* `options` - Mapping. The keys and values contained within are processed by
  sambacc and become part of the global values in smb.conf (or functional
  equivalent) when running a Samba server.

If a configuration section names more than one globals section. All of the
options within will be merged together to produce a single list of Samba
configuration globals.


## Users Section

The `users` section defines local users for a non-domain-member server
instance.

The `users` section supports one key, `all_entries`, which is a list of
user entries. Each user entry is as follows:
* `name` - The user's name.
* `password` - Optional. A plain-text password.
* `nt_hash` - Optional. An NT-Hashed password.
* `uid` - Optional integer. Specify the exact Unix UID the user should have.
* `gid` - Optional integer. Specify the exact Unix GID the user should have.

One of either `password` or `nt_hash` must be specified.

> **Warning**
> Do not consider `nt_hash`ed passwords as secure as the algorithm used to
> generate these hashes is weak (unsalted MD4). Use it only as a method to
> obscure the original password from casual viewers.

The NT-Hashed password can be generated by the following python snippet:
> hashlib.new('md4', password.encode('utf-16-le')).hexdigest().upper()

This may fail on some systems if the md4 hash has been disabled. Enabling
the hash is left as an exercise for the reader.


## Groups Section

The `groups` section defines local groups for a non-domain-member server
instance.

The `groups` section supports one key, `all_entries`, which is a list of
group entries. Each group entry is as follows:
* `name` - The user's name.
* `gid` - Optional integer. Specify the exact Unix GID the group should have.


## Domain Settings Section

The `domain_settings` sections defines configuration for AD DC
instances. The `domain_settings` section contains a mapping of domain
settings names to a domain-settings configuration block.

Each domain configuration section is as follows:
* `realm` - Name of the domain in kerberos realm form.
* `short_domain` - Optional. The short (nt-style) name of the domain.
* `admin_password` - The default password for the administrator user.
* `interfaces` - An optional subsection for dynamically configuring the network
  interfaces the domain controller will use. See below.

#### Interfaces Section

The interfaces section enables the sambacc tool to dynamically configure what
network interfaces will be enabled when the domain is provisioned.  On some
systems and in some environments there may be "bogus" network interfaces that
one does not want to enable the domain controller for. Examples include
interfaces related to virtualization or container engines that would cause the
DC to include a private or otherwise inaccessable IP to be included in the DNS
record(s) for the domain & domain controller.

The loopback device ("lo") is always enabled.

* `include_pattern` - Optional string. A regular expression that must match
  the name of an interface for that interface to be included.
  Example: `^eno[0-9]+$`
* `exclude_pattern` - Optional string. A regular expression that must not
  match the name of an interface for that interface to be included.
  The `exclude_pattern` option takes precedence over the `include_pattern`
  option.
  Example: `^(docker|virbr)[0-9]+$`

These options are intended to automate the act of examining a host's interfaces
prior to deployment and creating a list of suitable interfaces prior to setting
the "interfaces" and "bind interfaces only" parameters.  See the [Samba
Wiki page](https://wiki.samba.org/index.php/Setting_up_Samba_as_an_Active_Directory_Domain_Controller#Parameter_Reference)
for more details on this operation.


## Domain Groups Section

The `domain_groups` section defines initial groups that will be
automatically added to a newly provisioned domain. This section
is a mapping of the domain settings name to a list of domain group
entries.

A domain group entry is as follows:
* `name` - The name of the domain group.


## Domain Users Section
The `domain_users` section defines initial users that will be
automatically added to a newly provisioned domain. This section
is a mapping of the domain settings name to a list of domain user
entries.

A domain user entry is as follows:
* `name` - The name of the user.
* `surname` - A surname for the user.
* `given_name` - A given name for the user.
* `password` - A plain-text password.
* `member_of` - Optional. List of group names. The user will be added to the listed
  groups.


# YAML

The [YAML](https://yaml.org/) format may be used to configure sambacc when
PyYAML library is available. The YAML configuration is effectively converted to
JSON internally when processed. All of the documentation applying to the JSON
based configuration applies but in a somewhat easier to write format. The
filename must end with `.yaml` or `.yml` for sambacc to parse the file as YAML.

An example of a YAML based configuration file:
```yaml
samba-container-config: v0
# Define top-level configurations
configs:
  try2:
    globals: ["default"]
    shares:
      - "example"
      - "Other Name"
# Define Global Options
globals:
  default:
    options:
      load printers: "no"
      printing: "bsd"
      printcap name: "/dev/null"
      disable spoolss: "yes"
      guest ok: "no"
      security: "user"
      server min protocol: "SMB2"
# Define Shares
shares:
  example:
    options:
      path: /srv/a
      read only: "no"
  Other Name:
    options:
      path: /srv/b
      read only: "no"
# Define users
users:
  all_entries:
    - {"name": "sambauser", "password": "samba"}
    - {"name": "otheruser", "password": "insecure321"}
```

# TOML

The [TOML](https://toml.io/en/) format may be used to configure sambacc when
used on Python 3.11 or later or when the tomli library is available. The TOML
format may seem similar to the INI-style format used by Samba.  The TOML
configuration is effectively converted to JSON internally when processed. All
of the documentation applying to the JSON based configuration applies but in a
somewhat easier to read and write format. The filename must end with `.toml` for
sambacc to parse the file as TOML.

An example of a TOML based configuration file:
```toml
samba-container-config = "v0"

# Define top level configurations
[configs.try1]
globals = ["default"]
shares = ["example", "Other Name"]

# Define shares
[shares.example.options]
path = "/srv/a"
"read only" = "no"

[shares."Other Name".options]
path = "/srv/b"
"read only" = "no"

# Define global options
[globals.default.options]
"load printers" = "no"
printing = "bsd"
"printcap name" = "/dev/null"
"disable spoolss" = "yes"
"guest ok" = "no"
security = "user"
"server min protocol" = "SMB2"

# Define users
[[users.all_entries]]
name = "sambauser"
password = "samba"

[[users.all_entries]]
name = "otheruser"
password = "insecure321"
```
