#!/bin/bash

set -e

python=python3
url="https://github.com/samba-in-kubernetes/sambacc"
bdir="/var/tmp/build/sambacc"
distname="${SAMBACC_DISTNAME}"
# use SAMBACC_BUILD_TASKS to limit build tasks if needed
tasks="${SAMBACC_BUILD_TASKS:-task_test_tox task_py_build task_rpm_build task_gen_sums}"

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
    ddir="/srv/dist/$dname"
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

task_test_tox() {
    # Run tox with sitepackages enabled to allow access to system installed samba
    # modules. The container env already provides us control over the env.
    info "running test suite with tox"
    tox
}

task_py_build() {
    info "building python package(s)"
    pip -qq install build
    if [ "$distname" ]; then
        # building for a given "distribution name" - meaning this could be
        # consumed externally
        distdir="$(get_distdir "$distname")"
        info "using dist dir: $distdir"
        $python -m build --outdir "$distdir"
    else
        # just run the build as a test to make sure it succeeds
        $python -m build
    fi
}

task_rpm_build() {
    if ! [ "$distname" ]; then
        return
    fi
    if ! command -v rpmbuild ; then
        info "rpmbuild not found ... skipping"
        return
    fi

    distdir="$(get_distdir "$distname")"
    info "using dist dir: $distdir"
    for spkg in "$distdir/sambacc"-*.tar.gz; do
        info "RPM build for: ${spkg}"
        ver="$(basename  "${spkg}" | sed -e 's/^sambacc-//' -e 's/.tar.gz$//')"
        if echo "$ver" | grep -q "+" ; then
            rversion="$(echo "${ver}" | sed -e 's/\.dev/~/' -e 's/+/./')"
        else
            rversion="$ver"
        fi
        info "Using rpm-version=${rversion} pkg-version=${ver}"
        rpmbuild --nocheck -ta \
            -D "pversion ${ver}" -D"rversion ${rversion}" \
            -D "_rpmdir ${distdir}/RPMS" \
            -D "_srcrpmdir ${distdir}/SRPMS" \
            "$spkg"
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


# Allow the tests to use customized passwd file contents in order
# to test samba passdb support. It's a bit strange, but should work.
# The test suite tries to restore the passwd file after changing it,
# but you probably don't want to enable these on your desktop.
# TODO: actually use nss-wrapper
export WRITABLE_PASSWD=yes
export NSS_WRAPPER_PASSWD=/etc/passwd
export NSS_WRAPPER_GROUP=/etc/group


setup_fetch "$2"
cd "${bdir}"
setup_update "$1"

chk task_test_tox
chk task_py_build
chk task_rpm_build
chk task_gen_sums
