#
# sambacc: a samba container configuration tool
# Copyright (C) 2024  John Mulligan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#

from unittest import mock

import pytest

from sambacc.commands import skips


@pytest.mark.parametrize(
    "value,rtype",
    [
        ("always:", skips.SkipAlways),
        ("file:/var/lib/womble", skips.SkipFile),
        ("file:!/var/lib/zomble", skips.SkipFile),
        ("env:LIMIT==none", skips.SkipEnv),
        ("env:LIMIT!=everybody", skips.SkipEnv),
        ("env:LIMIT=everybody", ValueError),
        ("env:LIMIT", ValueError),
        ("file:", ValueError),
        ("always:forever", ValueError),
        ("klunk:", KeyError),
    ],
)
def test_parse(value, rtype):
    if issubclass(rtype, BaseException):
        with pytest.raises(rtype):
            skips.parse(value)
        return
    skf = skips.parse(value)
    assert isinstance(skf, rtype)


@pytest.mark.parametrize(
    "value,ret",
    [
        ("file:/var/lib/foo/a", "skip-if-file-exists: /var/lib/foo/a exists"),
        (
            "file:!/var/lib/bar/a",
            "skip-if-file-missing: /var/lib/bar/a missing",
        ),
        ("file:/etc/blat", None),
        ("env:PLINK==0", "env var: PLINK -> 0 == 0"),
        ("env:PLINK!=88", "env var: PLINK -> 0 != 88"),
        ("env:PLONK==enabled", None),
        ("always:", "always skip"),
    ],
)
def test_method_test(value, ret, monkeypatch):
    def _exists(p):
        rv = p.startswith("/var/lib/foo/")
        return rv

    monkeypatch.setattr("os.path.exists", _exists)
    monkeypatch.setenv("PLINK", "0")
    monkeypatch.setenv("PLONK", "disabled")
    skf = skips.parse(value)
    ctx = mock.MagicMock()
    assert skf.test(ctx) == ret


def test_test(monkeypatch):
    def _exists(p):
        rv = p.startswith("/var/lib/foo/")
        return rv

    monkeypatch.setattr("os.path.exists", _exists)
    monkeypatch.setenv("PLINK", "0")
    monkeypatch.setenv("PLONK", "disabled")

    conds = [
        skips.SkipEnv("==", "PLINK", "1"),
        skips.SkipEnv("!=", "PLONK", "disabled"),
        skips.SkipAlways(),
    ]
    ctx = mock.MagicMock()
    assert skips.test(ctx, conditions=conds) == "always skip"
    conds = conds[:-1]
    assert not skips.test(ctx, conditions=conds)
    monkeypatch.setenv("PLINK", "1")
    assert skips.test(ctx, conditions=conds) == "env var: PLINK -> 1 == 1"

    ctx.cli.skip_conditions = conds
    assert skips.test(ctx) == "env var: PLINK -> 1 == 1"


def test_help_info():
    txt = skips._help_info()
    assert "file:" in txt
    assert "env:" in txt
    assert "always:" in txt


def test_parse_hack():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        skips.parse("?")
