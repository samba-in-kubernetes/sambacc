# sambacc - A Samba Container Configuration Tool

## About

The sambacc is an experimental project that aims to consolidate configuration
of samba, and related components, running in a container. The configuation of
one or many containers is provided to the tool as JSON which then handles the
low level details of actually configuring smbd and other parts of the container
environment.


## Rationale

Samba is a powerful and unique tool for implementing the SMB protocol and a
software stack to support it on unix-like systems. However, it's potentially
challenging to set up and manage many instances of Samba by-hand, especially
when running under a container orchestration system.

The idea is to first automate all of the low level steps of setting up smbd,
users, groups, and other supporting configuration files. The tool is also
designed to consume one "global" configuration that can be maintained across
many container instances. sambacc is written in Python as samba provides Python
bindings for some of the aspects of samba we need to control.


## Usage

When installed a `samba-container` command will be available.

Without any additional arguments `samba-container` prints the synthesizsed
samba (smb.conf) configuration based on the environment variables:
* `SAMBACC_CONFIG` - configuration file(s)
* `SAMBA_CONTAINER_ID` - Identity of this instance

Additionally, there are subcommands:
* `samba-container import` - Import smb.conf-style settings into registry
* `samba-container import-users` - Import users into /etc files and smb passdb
* `samba-container init` - Initialize the container environment for use
  by samba services
* `samba-container run <service>` - Initialize and run a named samba service


## Install

Currently the only method of install is from source control.

* Clone the repo: `hg clone https://hg.sr.ht/~phlogistonjohn/sambacc`
* `cd sambacc`
* Install locally: `python setup.py install --user`

The typical setup.py commands should work.

Optional:
* Run tests: `tox`


## TODO

A lot.

Currently, the tool can create (local) users and groups, and configure and
start smbd. In the short term it needs much more testing (real-world, not unit)
to take it from just a proof-of-concept to something useful. It needs winbind
support to make it useful for Active Directory use cases. Potentially, we
also want to support scaling out across multiple instances, so we may also
need to integrate with ctdb.

The test suite has OKish coverage, but needs to handle more, especially the
samba passdb loader module.

Because of the system level dependencies, I've created a container image
for testing and building sambacc. It lives at ./tests/container. I'd like
to make this the canonical way to run all the tests, locally on the desktop
or in CI, but it needs fleshing out.


## License

GPLv3 as per the COPYING file.

This is the same license as used by Samba.
