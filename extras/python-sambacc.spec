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

%global _description %{expand:
A Python library and set of CLI tools intended to act as a bridge between a container
environment and Samba servers and utilities. It aims to consolidate, coordinate and
automate all of the low level steps of setting up smbd, users, groups, and other
supporting components.
}

%description %_description

%package -n python3-%{bname}
Summary: %{summary}
# Distro requires that are technially optional for the lib
Requires: python3-samba
Requires: python3-pyxattr

%description -n python3-%{bname}  %_description


%prep
%autosetup -n %{bname}-%{pversion}

%generate_buildrequires
%pyproject_buildrequires -e py3


%build
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files %{bname}


%check
%tox -e py3


%files -n python3-%{bname} -f %{pyproject_files}
%doc README.*
%{_bindir}/samba-container
%{_bindir}/samba-dc-container
%{_datadir}/%{bname}/examples/


%changelog
