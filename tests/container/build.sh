#!/bin/sh

python=python3
url="http://hg.sr.ht/~phlogistonjohn/sambacc"

mkdir -p /var/tmp/build/
bdir="/var/tmp/build/sambacc"

if [ -d "$bdir" ] && hg --cwd "$bdir" log -r. ; then
    echo "repo already checked out"
else
    hg clone "$url" "$bdir"
fi

set -e
cd "$bdir"
tox

$python setup.py sdist
$python setup.py bdist_wheel
