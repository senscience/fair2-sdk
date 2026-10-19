"""Names of the tables and columns.

Tables and columns are named after the record sets and fields of the metadata: their `name`, or the
suffix of their `@id` if they have none, as they are. Names are quoted in SQL, e.g.
`FROM "ML Cell Metadata"`, so any non-empty name is a valid identifier.
"""

from __future__ import annotations

import re


def name_of(node) -> str:
    """The SQL name of a record set or a field: its name, or the suffix of its @id if it has none.

    The suffix is what follows the last "/" or "#": "plain_text" for a record set @id expanded to
    "https://example.org/plain_text", "title" for the field "plain_text/title".
    """
    if node.name and node.name.strip():
        return node.name
    return re.split(r"[/#]", node.id.rstrip("/#"))[-1]


def assign_table_names(record_sets) -> tuple[dict[str, str], dict[str, str]]:
    """Table names (record set @id -> name), and the record sets skipped because of a conflict.

    DuckDB compares identifiers case-insensitively: a record set whose name is already taken by a
    previous one (e.g. "Donors" and "donors") is skipped instead of replacing its table.
    """
    names, conflicts, used = {}, {}, {}
    for record_set in record_sets:
        name = name_of(record_set)
        if name.lower() in used:
            conflicts[record_set.id] = (
                f"table name {name!r} is already used by record set {used[name.lower()]!r}"
            )
        else:
            used[name.lower()] = record_set.id
            names[record_set.id] = name
    return names, conflicts
