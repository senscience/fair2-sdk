"""The outcome of the steps that turn a record set into a table: a value, or why there is none."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Registered:
    """The table or view of a record set was created."""

    table: str


@dataclasses.dataclass(frozen=True)
class Skipped:
    """A record set has no table, and why."""

    reason: str


# What a format's register() returns.
Registration = Registered | Skipped
