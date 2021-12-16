# sambacc - A Samba Container Configuration Tool

## About

The sambacc is an young project that aims to consolidate and coordinate
configuration of [Samba](http://samba.org), and related components, when
running in a container. The configuation of one or many instances can be
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

The sambacc library and samba-container cli command are used by the
[samba-container project](https://github.com/samba-in-kubernetes/samba-container/)
as part of the server container images.


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

For complete usage, run:

```sh
samba-container --help
```


## Features

* Abstracts away some of the nitty-gritty details about what Samba expects
  in it's environment
* Imports specific smb.conf settings from "site wide" JSON configuration.
* Imports users and groups
* Starts smbd with container friendly settings
* Starts winbindd with container friendly settings
* Primitive and insecure support for joining AD

### TODO

A lot. Important features that are missing include:

* The ability to manage more secure domain joins
* Better coordination around dependent actions, like being joined
* Better integration (as opposed to unit) testing
* (Possibly) CTDB integration for scale out use cases


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
