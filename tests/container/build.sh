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

tox

$python setup.py sdist
$python setup.py bdist_wheel
