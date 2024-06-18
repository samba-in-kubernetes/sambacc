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

from typing import Optional
import argparse
import os

from sambacc.typelets import Self

from .cli import Context


class SkipIf:
    """Base class for objects used to check if a particular sambacc command
    should be skipped.
    Skips are useful when different commands are chained together
    unconditionally in a configuration file (like k8s init containers) but
    certain commmands should not be run.
    """

    NAME: str = ""

    def test(self, ctx: Context) -> Optional[str]:
        """Return a string explaining the reason for the skip or None
        indicating no skip is desired.
        """
        raise NotImplementedError()  # pragma: nocover

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse a string into a skip class arguments."""
        raise NotImplementedError()  # pragma: nocover


class SkipFile(SkipIf):
    """Skip execution if a file exists or does not exist.
    The input value "file:/foo/bar" will trigger a skip if the file /foo/bar
    exists. To skip if a file does not exist, use "file:!/foo/bar" - prefix the
    file name with an exclaimation point.
    """

    NAME: str = "file"
    inverted: bool = False
    path: str = ""

    @classmethod
    def parse(cls, value: str) -> Self:
        obj = cls()
        if not value:
            raise ValueError("missing path")
        if value[0] == "!":
            obj.inverted = True
            value = value[1:]
        obj.path = value
        return obj

    def test(self, ctx: Context) -> Optional[str]:
        exists = os.path.exists(self.path)
        if self.inverted and not exists:
            return f"skip-if-file-missing: {self.path} missing"
        if not self.inverted and exists:
            return f"skip-if-file-exists: {self.path} exists"
        return None


class SkipEnv(SkipIf):
    """Skip execution if an environment variable is, or is not, equal to a
    value. The specification is roughly "env:<ENV_VAR><op><VALUE>" where op may
    be either `==` or `!=`. For example, "env:FLAVOR==cherry" will skip
    execution if the environment variable "FLAVOR" contains the value "cherry".
    "env:FLAVOR!=cherry" will skip execution if "FLAVOR" contains any value
    other than "cherry".
    """

    NAME: str = "env"
    _EQ = "=="
    _NEQ = "!="

    def __init__(self, op: str, var_name: str, value: str) -> None:
        self.op = op
        self.var_name = var_name
        self.target_value = value

    @classmethod
    def parse(cls, value: str) -> Self:
        if cls._EQ in value:
            op = cls._EQ
        elif cls._NEQ in value:
            op = cls._NEQ
        else:
            raise ValueError("invalid SkipEnv: missing or invalid operation")
        lhv, rhv = value.split(op, 1)
        return cls(op, lhv, rhv)

    def test(self, ctx: Context) -> Optional[str]:
        env_val = os.environ.get(self.var_name)
        if self.op == self._EQ and env_val == self.target_value:
            return (
                f"env var: {self.var_name}"
                f" -> {env_val} {self.op} {self.target_value}"
            )
        if self.op == self._NEQ and env_val != self.target_value:
            return (
                f"env var: {self.var_name}"
                f" -> {env_val} {self.op} {self.target_value}"
            )
        return None


class SkipAlways(SkipIf):
    """Skip execution unconditionally. Must be specified as "always:" and takes
    no value after the colon.
    """

    NAME: str = "always"

    @classmethod
    def parse(cls, value: str) -> Self:
        if value:
            raise ValueError("always skip takes no value")
        return cls()

    def test(self, ctx: Context) -> Optional[str]:
        return "always skip"


_SKIP_TYPES = [SkipFile, SkipEnv, SkipAlways]


def test(
    ctx: Context, *, conditions: Optional[list[SkipIf]] = None
) -> Optional[str]:
    """Return a string explaining the reason for a skip or None indicating
    no skip should be performed. Typically the skip conditions will be
    derived from the command line arguments but can be passed in manually
    using the `conditions` keyword argument.
    """
    if not conditions:
        conditions = ctx.cli.skip_conditions or []
    for cond in conditions:
        skip = cond.test(ctx)
        if skip:
            return skip
    return None


def parse(value: str) -> SkipIf:
    """Given a string return a SkipIf-based object. Every value must be
    prefixed with the skip "type" (the skip type's NAME).
    """
    if value == "?":
        # A hack to avoid putting tons of documentation into the help output.
        raise argparse.ArgumentTypeError(_help_info())
    for sk in _SKIP_TYPES:
        assert issubclass(sk, SkipIf)
        prefix = f"{sk.NAME}:"
        plen = len(prefix)
        if value.startswith(prefix):
            return sk.parse(value[plen:])
    raise KeyError("no matching skip rule for: {value!r}")


def _help_info() -> str:
    msgs = ["Skip conditions help details:", ""]
    for sk in _SKIP_TYPES:
        assert issubclass(sk, SkipIf)
        msgs.append(f"== Skip execution on condition `{sk.NAME}` ==")
        assert sk.__doc__
        for line in sk.__doc__.splitlines():
            msgs.append(line.strip())
        msgs.append("")
    return "\n".join(msgs)
