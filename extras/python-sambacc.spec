%global bname sambacc
# set xversion to define the default version number
%define xversion 0.1
# set pversion for a customized python package version string
%{?!pversion: %define pversion %{xversion}}
# set rversion for a customized rpm version
%{?!rversion: %define rversion %{xversion}}


Name:           python-%{bname}
Version:        %{rversion}
Release:        1%{?dist}
Summary:        Samba Container Configurator

License:        GPLv3+
URL:            https://github.com/samba-in-kubernetes/sambacc
# sambacc is not released yet so we're leaving off the url for now
# once packaged and released we can update this field
Source:         %{bname}-%{pversion}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
# we need python3-samba as a build dependency in order to run
# the test suite
BuildRequires:  python3-samba
# ditto for the net binary
BuildRequires: /usr/bin/net

%global _description %{expand:
A Python library and set of CLI tools intended to act as a bridge between a container
environment and Samba servers and utilities. It aims to consolidate, coordinate and
automate all of the low level steps of setting up smbd, users, groups, and other
supporting components.
}

%description %_description

%package -n python3-%{bname}
Summary: %{summary}
# Distro requires that are technically optional for the lib
Requires: python3-samba
Requires: python3-pyxattr
%if 0%{?fedora} >= 37 || 0%{?rhel} >= 9
# Enable extras other than validation as the dependency needed
# is too old on centos/rhel 9.
Recommends: %{name}+toml
Recommends: %{name}+yaml
Recommends: %{name}+rados
%endif
%if 0%{?fedora} >= 37
Recommends: %{name}+validation
%endif

%description -n python3-%{bname}  %_description


%prep
%autosetup -n %{bname}-%{pversion}

%generate_buildrequires
%pyproject_buildrequires -e py3-sys


%build
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files %{bname}


%check
%tox -e py3-sys


%files -n python3-%{bname} -f %{pyproject_files}
%doc README.*
%{_bindir}/samba-container
%{_bindir}/samba-dc-container
%{_datadir}/%{bname}/examples/


%pyproject_extras_subpkg -n python3-%{bname} validation
%pyproject_extras_subpkg -n python3-%{bname} toml
%pyproject_extras_subpkg -n python3-%{bname} yaml
%pyproject_extras_subpkg -n python3-%{bname} rados


%changelog
%autochangelog
