#!/bin/bash

set -e

python=python3
url="https://github.com/samba-in-kubernetes/sambacc"
bdir="/var/tmp/build/sambacc"
distname="${SAMBACC_DISTNAME}"

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

# allow customizing the repo on the cli or environment
if [ "$2" ]; then
    url="$2"
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

cd "${bdir}"

if [ "$1" ]; then
    # a tag or revision id was specified on the cli
    update "${bdir}" "$1"
fi

# Allow the tests to use customized passwd file contents in order
# to test samba passdb support. It's a bit strange, but should work.
# The test suite tries to restore the passwd file after changing it,
# but you probably don't want to enable these on your desktop.
# TODO: actually use nss-wrapper
export WRITABLE_PASSWD=yes
export NSS_WRAPPER_PASSWD=/etc/passwd
export NSS_WRAPPER_GROUP=/etc/group

# Run tox with sitepackages enabled to allow access to system installed samba
# modules. The container env already provides us control over the env.
info "running test suite with tox"
tox

info "building python package(s)"
pip -qq install build
if [ "$distname" ]; then
    # building for a given "distribution name" - meaning this could be
    # consumed externally
    distdir="/srv/dist/$distname"
    info "using dist dir: $distdir"
    mkdir -p "$distdir"
    $python -m build --outdir "$distdir"
    (cd "$distdir" && sha512sum * > "$distdir/sha512sums")
else
    # just run the build as a test to make sure it succeeds
    $python -m build
fi
