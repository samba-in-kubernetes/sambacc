# sambacc - A Samba Container Configuration Tool

## About

The sambacc project aims to consolidate and coordinate configuration of
[Samba](http://samba.org), and related components, when running in a
container. The configuration of one or many server instances can be
managed by the tool with the use of configuration files.  These
configuration files act as a superset of the well-known smb.conf, to
configure Samba, as well as other low level details of the container
environment.


## Rationale

Samba is a powerful and unique tool for implementing the SMB protocol and
a software stack to support it on unix-like systems. However, it's
potentially challenging to set up and manage many instances of Samba
by-hand, especially when running under a container orchestration system.

The idea behind sambacc is to automate much of the low level steps needed
to set up samba daemons, users, groups, and other supporting
components. The tool is also designed to consume configuration files that
can be used across many container instances. sambacc is written in Python
as samba provides Python bindings for some of the aspects of samba we need
to control.

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
  in its environment
* Imports specific smb.conf settings from "site wide" configuration files.
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

Contributions and feedback would be very much appreciated.


## Install

The sambacc library, samba-container command, and samba-dc-container are
written assuming the software is being run within an OCI container environment.
While there's nothing stopping you from trying to install it on something else
the value of doing that will be rather limited.

The [samba-container
project](https://github.com/samba-in-kubernetes/samba-container) includes
sambacc and samba packages. If you are looking to use sambacc and not
contribute to it, that's probably what you want.

Builds of sambacc are continuously produced within our [COPR repository](https://copr.fedorainfracloud.org/coprs/phlogistonjohn/sambacc/).
These builds are then consumed by the container image builds.

Otherwise, the only method of install is from source control.

* Clone the repo: `git clone https://github.com/samba-in-kubernetes/sambacc`
* `cd sambacc`
* Install locally: `python -m pip install --user .`

The test & build container may also be used to build source tarballs and
wheels. Then you can distribute and install from the wheel if you need to.

### Testing

#### Local testing

To run the entire unit test suite locally install `tox` and run `tox` in
the repo root.

Because of the library and tooling that interacts with samba has some
system level dependencies, not all tests can be run locally in
isolated (virtualenv) environments.


#### Containerized testing

A more robust and isolated testing environment is provided in
the form of the sambacc container image.

The container file and other sources are available at ./tests/container in
the sambacc repo. This is the canonical way to run the test suite and is
what is used by the CI tests. When run this way certain system packages
can be installed, etc. to support running a wider range of test cases.

By default the container image is configured to check out sambacc master
branch and execute the tests and build python source distributions,
wheels, and RPM packages. You can test your local git checkout using the
image by mounting it at /var/tmp/build/sambacc (example: `podman run -v
$PWD:/var/tmp/build/sambacc sambacc:ci`).

To access the packages that are built using the container, mount a
directory into the container at "/srv/dist" and set the environment
variable `SAMBACC_DISTNAME` to a term of your choice (example: "latest").
This will then save the builds in a directory of that name in your output
directory.
Example:
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

You can combine the source directory mount and distribution directory
mount in one command to produce builds for your own local development work
if needed.

## License

GPLv3 as per the COPYING file.

This is the same license as used by Samba.


## Contributing/Contact

Patches, issues, comments, and questions are welcome.

Resources:
* [Issue tracker](https://github.com/samba-in-kubernetes/sambacc/issues)
* [Discussions board](https://github.com/samba-in-kubernetes/sambacc/discussions)
