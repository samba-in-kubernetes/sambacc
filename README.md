# sambacc - A Samba Container Configuration Tool

## About

The sambacc is an young project that aims to consolidate and coordinate
configuration of [Samba](http://samba.org), and related components, when
running in a container. The configuration of one or many instances can be
provided to the tool by way of a JSON file which then handles the low level
details of actually configuring smbd and other elements in the container
environment.


## Rationale

Samba is a powerful and unique tool for implementing the SMB protocol and a
software stack to support it on unix-like systems. However, it's potentially
challenging to set up and manage many instances of Samba by-hand, especially
when running under a container orchestration system.

The idea behind sambacc is mainly to automate all of the low level steps of
setting up smbd, users, groups, and other supporting components. The tool is
also designed to consume one "site-wide" configuration file that can be
maintained across many container instances. sambacc is written in Python as
samba provides Python bindings for some of the aspects of samba we need to
control.

The sambacc library and samba-container CLI command are used by the
[samba-container project](https://github.com/samba-in-kubernetes/samba-container/)
as part of the server container images.


## Usage

### File Server

The `samba-container` command is used to manage features related to
the Samba file server and closely related components.

Without any additional arguments `samba-container` prints the synthesised
samba (smb.conf) configuration based on the environment variables:
* `SAMBACC_CONFIG` - configuration file(s)
* `SAMBA_CONTAINER_ID` - Identity of this instance

Additionally, there are many other subcommands the tool supports. These include:
* `samba-container import` - Import smb.conf-style settings into registry
* `samba-container import-users` - Import users into /etc files and smb passdb
* `samba-container init` - Initialize the container environment for use
  by samba services
* `samba-container run <service>` - Initialize and run a named samba service

For a complete description of the subcommands supported, run:

```sh
samba-container --help
```

### Active Directory Domain Controller

The `samba-dc-container` command is used to manage features related to
the Samba AD DC server and related components.

Currently, `samba-dc-container` supports one subcommand. The `run` subcommand
is used to start an AD DC server. This command supports various setup steps
including steps to join an existing domain, provision a new domain,
populate a domain with stock users/groups, etc.

For a complete description of the subcommands supported, run:

```sh
samba-dc-container --help
```


## Features

* Abstracts away some of the nitty-gritty details about what Samba expects
  in it's environment
* Imports specific smb.conf settings from "site wide" JSON configuration.
* Imports users and groups
* Starts smbd with container friendly settings
* Starts winbindd with container friendly settings
* Support for joining AD
* Support for managing CTDB clustering
* Support for creating/joining Samba Active Directory servers

### Major TODOs

A lot. Various things that are missing include:

* Features to perform more secure (password-less) domain joins
* Better integration (as opposed to unit) testing
* Better use of APIs versus executing CLI commands


## Install

Currently the only method of install is from source control.

* Clone the repo: `git clone https://github.com/samba-in-kubernetes/sambacc`
* `cd sambacc`
* Install locally: `python -m pip install --user .`

The test & build container may also be used to build source tarballs and
wheels. Then you can distribute and install from the wheel if you need to.

### Testing

#### Local testing

To run the entire unit test suite locally install `tox` and run `tox` in
the repo root.

Because of the library and tooling that interacts with samba has some system level dependencies, not all test can be run locally.

#### Containerized testing

In addition to running the unit tests locally, I've created a container image
for testing and building sambacc. It lives at ./tests/container. This is
canonical way to run the test suite and is what is used by the CI tests. When
run this way certain system packages can be installed, etc. to support
running a wider range of test cases.

To produce builds using the container, mount a directory into the container at
"/srv/dist" and set the environment variable `SAMBACC_DISTNAME` to a term of
your choice (example: "latest"). This will then save the builds in a dir of
that name in your output dir. Example:
```
$ mkdir -p $HOME/tmp/sambacc
$ podman run --rm \
  -v $HOME/tmp/sambacc:/srv/dist -e SAMBACC_DISTNAME=latest \
  quay.io/samba.org/sambacc:latest
$ ls $HOME/tmp/sambacc
latest
$ ls $HOME/tmp/sambacc/latest
sambacc-0.1.dev225+g10059ff-py3-none-any.whl  sha512sums
sambacc-0.1.dev225+g10059ff.tar.gz
```

## License

GPLv3 as per the COPYING file.

This is the same license as used by Samba.


## Contributing/Contact

Patches, issues, comments, and questions are welcome.

Resources:
* [Issue tracker](https://github.com/samba-in-kubernetes/sambacc/issues)
* [Discussions board](https://github.com/samba-in-kubernetes/sambacc/discussions)
