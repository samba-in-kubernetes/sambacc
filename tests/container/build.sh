#!/bin/sh

python=python3
url="https://hg.sr.ht/~phlogistonjohn/sambacc"

mkdir -p /var/tmp/build/
bdir="/var/tmp/build/sambacc"

if [ -d "$bdir" ] && hg --cwd "$bdir" log -r. ; then
    echo "repo already checked out"
else
    hg clone "$url" "$bdir"
fi

set -e
cd "$bdir"

if [ "$1" ]; then
    # a revision id was specified on the cli
    hg update --check "$1"
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
tox --sitepackages

$python setup.py sdist
$python setup.py bdist_wheel
