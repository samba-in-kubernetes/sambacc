#!/bin/bash

set -e

python=python3
url="${SAMBACC_REPO_URL:-https://github.com/samba-in-kubernetes/sambacc}"
bdir="${SAMBACC_BUILD_DIR:-/var/tmp/build/sambacc}"
distname="${SAMBACC_DISTNAME}"
# use SAMBACC_BUILD_TASKS to limit build tasks if needed
tasks="${SAMBACC_BUILD_TASKS:-task_test_tox task_py_build task_rpm_build task_gen_sums}"
dist_prefix="${SAMBACC_DIST_PREFIX:-/srv/dist}"
dnf_cmd=dnf

info() {
    echo "[[sambacc/build]] $*"
}

checked_out() {
    local d="$1"
    # allow manual clones with either git or hg
    [[ -d "$d" && ( -d "$d/.git" || -d "$d/.hg" ) ]]
}

clone() {
    # if the script is doing the cloning we default to git
    # as obnoxxx has peer-pressured me into it
    git clone "$1" "$2"
}

update() {
    local d="$1"
    local node="$2"
    if [[ -d "$d/.hg" ]]; then
        hg update --check "${node}"
    else
        git checkout "${node}"
    fi
}

chk() {
    for x in $tasks; do
        case "$1" in
            "$x")
                # execute the named task if it is in $tasks
                "$1"
                return $?
            ;;
        esac
    done
    info "skipping task: $1"
}

get_distdir() {
    dname="$1"
    if [ "${dname}" ]; then
        ddir="${dist_prefix}/$dname"
    else
        ddir="/var/tmp/scratch_dist"
    fi
    mkdir -p "$ddir" >/dev/null
    echo "$ddir"
}

setup_fetch() {
    # allow customizing the repo on the cli or environment
    if [ "$1" ]; then
        url="$1"
    elif [ "${SAMBACC_REPO_URL}" ]; then
        url="${SAMBACC_REPO_URL}"
    fi

    mkdir -p /var/tmp/build/ || true
    if checked_out "${bdir}" ; then
        info "repo already checked out"
    else
        info "cloning sambacc repo"
        clone "$url" "${bdir}"
    fi
}

setup_update() {
    if [ "$1" ]; then
        # a tag or revision id was specified on the cli
        update "${bdir}" "$1"
    fi
}

task_sys_deps() {
    info "installing system packages"
    OS_VER=$(source /etc/os-release && echo "${ID}-${VERSION_ID}")
    case "${OS_VER}" in
        centos*)
            info "detected centos (stream): ${OS_VER}"
            use_centos=true
        ;;
        rhel*)
            info "detected rhel: ${OS_VER}"
            use_centos=
            use_rhel=true
        ;;
        fedora*)
            info "detected fedora: ${OS_VER}"
            use_centos=
        ;;
        *)
            info "unknown platform: ${OS_VER}"
            return 1
        ;;
    esac

    yum_args=("--setopt=install_weak_deps=False")
    pkgs=(\
        git \
        mercurial \
        python-pip \
        python-pip-wheel \
        python-setuptools \
        python-setuptools-wheel \
        python-tox \
        python3-samba \
        python3-wheel \
        python3-pyxattr \
        python3-devel \
        python3.9 \
        samba-common-tools \
        rpm-build \
        'python3dist(flake8)' \
        'python3dist(inotify-simple)' \
        'python3dist(mypy)' \
        'python3dist(pytest)' \
        'python3dist(pytest-cov)' \
        'python3dist(setuptools-scm)' \
        'python3dist(tox-current-env)' \
        'python3dist(wheel)' \
    )

    if [ "$use_centos" ]; then
        "${dnf_cmd}" install -y epel-release
        yum_args=(--enablerepo=crb)
        pkgs+=(pyproject-rpm-macros)
    fi
    if [ "$use_rhel" ]; then
        pkgs+=(pyproject-rpm-macros)
    fi
    "${dnf_cmd}" "${yum_args[@]}" install -y "${pkgs[@]}"
    "${dnf_cmd}" clean all
}

task_test_tox() {
    # Run tox with sitepackages enabled to allow access to system installed samba
    # modules. The container env already provides us control over the env.
    info "running test suite with tox"
    tox
}

task_py_build() {
    info "building python package(s)"
    pip -qq install build
    # if distname is set, then we are building for external consumption
    # if distname is not set then we're building for internal consumption
    # only
    distdir="$(get_distdir "$distname")"
    info "using dist dir: $distdir"

    # setuptools_scm calls into git, newer git versions have stricter ownership
    # rules that can break our builds when mounted into a container. Tell our
    # in-container git, that it's all ok and the monsters aren't real.
    # This config will vanish once the container exits anyway.
    git config --global --add safe.directory "${bdir}"
    $python -m build --outdir "$distdir"
}

task_rpm_build() {
    if ! command -v rpmbuild ; then
        info "rpmbuild not found ... skipping"
        return
    fi

    distdir="$(get_distdir "$distname")"
    local rpmbuild_stage="-ba"
    if [ "${SAMBACC_SRPM_ONLY}" ]; then
        rpmbuild_stage="-bs"
    fi
    info "using dist dir: $distdir; using stage: ${rpmbuild_stage}"
    for spkg in "$distdir/sambacc"-*.tar.gz; do
        info "RPM build for: ${spkg}"
        ver="$(basename  "${spkg}" | sed -e 's/^sambacc-//' -e 's/.tar.gz$//')"
        if echo "$ver" | grep -q "+" ; then
            rversion="$(echo "${ver}" | sed -e 's/\.dev/~/' -e 's/+/./')"
        else
            rversion="$ver"
        fi
        info "Using rpm-version=${rversion} pkg-version=${ver}"
        tdir="$(mktemp -d)"
        (
            echo "%define pversion ${ver}"
            echo "%define rversion ${rversion}"
            tar -xf "$spkg" -O \
                "sambacc-${ver}/extras/python-sambacc.spec"
        ) > "${tdir}/python-sambacc.spec"
        rpmbuild "${rpmbuild_stage}" \
            -D "_rpmdir ${distdir}/RPMS" \
            -D "_srcrpmdir ${distdir}/SRPMS" \
            -D "_sourcedir $(dirname "${spkg}")" \
            "${tdir}/python-sambacc.spec"
        rm -rf "${tdir}"
    done
}

task_gen_sums() {
    if [ "$distname" ]; then
        info "generating checksums"
        distdir="$(get_distdir "$distname")"
        info "using dist dir: $distdir"
        (cd "$distdir" && \
            find . -type f -not -name 'sha*sums' -print0 | \
            xargs -0 sha512sum  > "$distdir/sha512sums")
    fi
}

cleanup() {
    if [ -z "${distname}" ]; then
        info "cleaning scratch dist dir"
        rm -rf "$(get_distdir "$distname")"
    fi
}

if ! command -v "${dnf_cmd}" >/dev/null ; then
    dnf_cmd=yum
fi

# Allow the tests to use customized passwd file contents in order
# to test samba passdb support. It's a bit strange, but should work.
# The test suite tries to restore the passwd file after changing it,
# but you probably don't want to enable these on your desktop.
# TODO: actually use nss-wrapper
export WRITABLE_PASSWD=yes
export NSS_WRAPPER_PASSWD=/etc/passwd
export NSS_WRAPPER_GROUP=/etc/group

# when called with --install as the first argument, go into a special mode
# typically used to just install the container's dependency packages
if [[ "$1" = "--install" ]]; then
    task_sys_deps
    exit $?
fi

# if critical packages (currently just git) are missing we assume that
# we need to automatically enable the task_sys_deps step.
# this step is not enabled by default due to the overhead that updating
# the dnf repos creates on the overall build time.
if ! command -v git &>/dev/null ; then
    tasks="$tasks task_sys_deps"
fi

trap cleanup EXIT

chk task_sys_deps
setup_fetch "$2"
cd "${bdir}"
setup_update "$1"

chk task_test_tox
chk task_py_build
chk task_rpm_build
chk task_gen_sums
