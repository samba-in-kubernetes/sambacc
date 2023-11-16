# sambacc Release Process

## Preparation

Currently there is no dedicated branch for releases. sambacc is simple enough,
has few dependencies, and we're not planning on doing backports. Therefore
we apply release tags to the master branch.

```
git checkout master
git pull --ff-only
git tag -a -m 'Release v0.3' v0.3
```

This creates an annotated tag. Release tags must be annotated tags.

Perform a final check that all supported OSes build. You can
follow the commands below, which are based on the github workflows at the
time this document was written:

```
podman build --build-arg=SAMBACC_BASE_IMAGE=quay.io/centos/centos:stream9 -t sambacc:temp-centos9 tests/container/ -f tests/container/Containerfile
podman build --build-arg=SAMBACC_BASE_IMAGE=registry.fedoraproject.org/fedora:37 -t sambacc:temp-fc37 tests/container/ -f tests/container/Containerfile
podman build --build-arg=SAMBACC_BASE_IMAGE=registry.fedoraproject.org/fedora:38 -t sambacc:temp-fc38 tests/container/ -f tests/container/Containerfile

# name the last part after the release version
mybuild=$PWD/_builds/v03
mkdir -p $mybuild
# perform a combined test & build, that stores build artifacts under $mybuild/$SAMBACC_DISTNAME
podman run -v $PWD:/var/tmp/build/sambacc -v $mybuild:/srv/dist -e SAMBACC_DISTNAME=centos9 sambacc:temp-centos9
podman run -v $PWD:/var/tmp/build/sambacc -v $mybuild:/srv/dist -e SAMBACC_DISTNAME=fc37 sambacc:temp-fc37
podman run -v $PWD:/var/tmp/build/sambacc -v $mybuild:/srv/dist -e SAMBACC_DISTNAME=fc38 sambacc:temp-fc38

# view build results
ls -lR $mybuild
```

Modify the set of base OSes to match what is supported by the release. Check
that the logs show that tag version was correctly picked up by the build.
The python and rpm packages should indicate the new release version and not
include an "unreleased git version".

For at least one build, select a set of files that includes the source tarball,
the Python Wheel (.whl file), and a source RPM. Create or alter an existing
sha512sums file containing the sha512 hashes of these files.


## GitHub Release

When you are satisfied that the tagged version is suitable for release, you
can push the tag to the public repo:
```
git push --follow-tags
```

Manually trigger a COPR build. Confirm that new COPR build contains the correct
version number and doesn't include an "unreleased git version".
You will need to have a fedora account and the ability to trigger builds
for `phlogistonjohn/sambacc`.

Draft a new set of release notes. Select the recently pushed tag. Start with
the auto-generated release notes from github (activate the `Generate release
notes` button/link). Add an introductory section (see previous notes for an
example). Add a "Highlights" section if there are any notable features or fixes
in the release. The Highlights section can be skipped if the content of the
release is unremarkable (e.g. few changes occurred since the previous release).

Attach the source tarball, the Python Wheel, and one SRPM from the earlier
build(s), along with the sha512sums file to the release.

Perform a final round of reviews, as needed, for the release notes and then
publish the release.


## PyPI

There is a [sambacc repository on PyPI](https://pypi.org/project/sambacc/).
This exists mainly to reserve the sambacc name, however we desire to keep it up
to date too.  You will need to have a PyPI account and access to the sambacc
repo.

Log into PyPI web UI. (Re)Generate a pypi login token for sambacc.
Ensure `twine` is installed:
```
python3 -m pip install --upgrade twine
```

Create a directory to store the python build artifacts:
```
rm -rf _build/pypi
mkdir -p _build/pypi
cp sambacc-0.3.tar.gz sambacc-0.3-py3-none-any.whl _build/pypi
```
Upload the files to PyPI creating a new release:
```
python3 -m twine upload _build/pypi/*
# Supply a username of `__token__` and the password will be the value
of the token you acquiried above.
```

A new release like `https://pypi.org/project/sambacc/0.3/` should have become
available.
