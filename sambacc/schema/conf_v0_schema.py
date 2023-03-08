#!/usr/bin/python3
# --- GENERATED FILE --- DO NOT EDIT --- #
# --- generated from: conf-v0.schema.yaml

SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "mailto:phlogistonjohn+sambacc-v0@asynchrono.us",
    "title": "sambacc configuration",
    "description": (
        "The configuration for the sambacc tool. sambacc configures Samba and"
        " the container\nenvironment to fit Samba's unique needs. This"
        " configuration can hold configuration\nfor more than one server"
        ' "instance". The "configs" section contains one or'
        " more\nconfiguration with a name that can be selected at runtime."
        " Share definitions\nand samba global configuration blocks can be"
        " mixed and matched.\n"
    ),
    "type": "object",
    "$defs": {
        "section_choices": {
            "description": (
                "Selects sub-sections from elsewhere in the configuration.\n"
            ),
            "type": "array",
            "items": {"type": "string"},
        },
        "feature_flags": {
            "description": (
                "Feature flags are used to enable specific, wide-ranging,"
                " features of\nsambacc. For example, it is used to enable"
                " clustered mode with ctdb.\n"
            ),
            "type": "array",
            "items": {"enum": ["addc", "ctdb"]},
        },
        "samba_options": {
            "description": (
                "A mapping of values that will be passed into the smb.conf"
                " (or equivalent)\nto directly configure Samba.\n"
            ),
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "permissions_config": {
            "description": (
                "Settings that enable and manage sambacc's permissions"
                " management support.\n"
            ),
            "type": "object",
            "properties": {
                "method": {
                    "description": (
                        "Backend method for controlling permissions on shares"
                    ),
                    "type": "string",
                },
                "status_xattr": {
                    "description": (
                        "xattr name used to store permissions state"
                    ),
                    "type": "string",
                },
            },
            "additionalProperties": {"type": "string"},
        },
        "user_entry": {
            "description": (
                "A user that will be instantiated in the local contianer"
                " environment to\nin order to provide access to smb shares.\n"
            ),
            "type": "object",
            "properties": {
                "name": {"description": "The user's name", "type": "string"},
                "uid": {
                    "description": "The Unix UID the user should have",
                    "type": "integer",
                },
                "gid": {
                    "description": "The Unix GID the user should have",
                    "type": "integer",
                },
                "nt_hash": {
                    "description": "An NT-Hashed password",
                    "type": "string",
                },
                "password": {
                    "description": "A plain-text password",
                    "type": "string",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "group_entry": {
            "description": (
                "A group that will be instantiated in the local contianer"
                " environment to\nin order to provide access to smb shares.\n"
            ),
            "type": "object",
            "properties": {
                "name": {"description": "The group name", "type": "string"},
                "gid": {
                    "description": "The Unix GID the group should have",
                    "type": "integer",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "domain_user_entry": {
            "description": (
                "A user that will be created in the specified AD domain."
                " These\nusers are populated in the directory after the"
                " domain is provisioned.\n"
            ),
            "type": "object",
            "properties": {
                "name": {"description": "The user's name", "type": "string"},
                "surname": {
                    "description": "A surname for the user",
                    "type": "string",
                },
                "given_name": {
                    "description": "A given name for the user",
                    "type": "string",
                },
                "uid": {"type": "integer"},
                "gid": {"type": "integer"},
                "nt_hash": {"type": "string"},
                "password": {
                    "description": "A plain-text password",
                    "type": "string",
                },
                "member_of": {
                    "description": (
                        "A list of group names that the user should belong to"
                    ),
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "domain_group_entry": {
            "description": (
                "A group that will be created in the specified AD domain."
                " These\ngroups are populated in the directory after the"
                " domain is provisioned.\n"
            ),
            "type": "object",
            "properties": {
                "name": {"description": "The group name", "type": "string"},
                "gid": {"type": "integer"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    "properties": {
        "samba-container-config": {
            "type": "string",
            "title": "Cofiguration Format Version",
            "description": (
                "A short version string that assists in allowing the"
                " configuration\nformat to (some day) support incompatible"
                " version changes.\n(It is unique to the configuration and is"
                " not the version of sambacc)\n"
            ),
        },
        "configs": {
            "title": "Container Configurations",
            "description": (
                "A mapping of named configurations (instances) to top-level"
                " configuration\nblocks. A useable configuration file must"
                " have at least one configuration,\nbut more than one is"
                " supported.\n"
            ),
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "shares": {"$ref": "#/$defs/section_choices"},
                    "globals": {"$ref": "#/$defs/section_choices"},
                    "instance_features": {"$ref": "#/$defs/feature_flags"},
                    "permissions": {"$ref": "#/$defs/permissions_config"},
                    "instance_name": {
                        "description": (
                            "A name that will be set for the server"
                            " instance.\n"
                        ),
                        "type": "string",
                    },
                    "domain_settings": {
                        "description": (
                            "The name of the domain settings. Only used with"
                            " 'ADDC' feature flag.\n"
                        ),
                        "type": "string",
                    },
                },
                "additionalProperties": False,
            },
        },
        "shares": {
            "description": (
                "A mapping of share name to share specific configuration. A"
                ' share can\nhave "options" that are passed to Samba. Shares'
                ' can have an optional\n"permissions" section for managing'
                " permissions/acls in sambacc.\n"
            ),
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "options": {"$ref": "#/$defs/samba_options"},
                    "permissions": {"$ref": "#/$defs/permissions_config"},
                },
                "additionalProperties": False,
            },
        },
        "globals": {
            "description": (
                "A mapping of samba global configuation blocks. The global"
                " section names\nare not passed to Samba. All sections"
                " selected by a configuration are\nmerged together before"
                " passing to Samba.\n"
            ),
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {"options": {"$ref": "#/$defs/samba_options"}},
                "additionalProperties": False,
            },
        },
        "domain_settings": {
            "description": (
                "A mapping of AD DC domain configuration keys to domain"
                " configurations.\nThese parameters are used when"
                " provisioning an AD DC instance.\n"
            ),
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "realm": {"type": "string"},
                    "short_domain": {"type": "string"},
                    "admin_password": {"type": "string"},
                },
                "required": ["realm"],
                "additionalProperties": False,
            },
        },
        "users": {
            "description": (
                "Users to add to the container environment in order to"
                " provide\nShare access-control wihout becoming a domain"
                " member server.\n"
            ),
            "type": "object",
            "properties": {
                "all_entries": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/user_entry"},
                }
            },
        },
        "groups": {
            "description": (
                "Groups to add to the container environment in order to"
                " provide\nShare access-control wihout becoming a domain"
                " member server.\n"
            ),
            "type": "object",
            "properties": {
                "all_entries": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/group_entry"},
                }
            },
        },
        "domain_users": {
            "description": (
                "The domain_users section defines initial users that will be"
                " automatically\nadded to a newly provisioned domain. This"
                " section is a mapping of the\ndomain settings name to a list"
                " of domain user entries.\n"
            ),
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"$ref": "#/$defs/domain_user_entry"},
            },
        },
        "domain_groups": {
            "description": (
                "The domain_groups section defines initial groups that will"
                " be\nautomatically added to a newly provisioned domain. This"
                " section is\na mapping of the domain settings name to a list"
                " of domain group entries.\n"
            ),
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"$ref": "#/$defs/domain_group_entry"},
            },
        },
        "ctdb": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
    "additionalProperties": False,
    "required": ["samba-container-config"],
    "patternProperties": {"^_": True},
}
