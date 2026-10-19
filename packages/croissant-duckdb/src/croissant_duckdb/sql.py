"""SQL helpers: quoting, and the select list renaming a file's columns to the field names."""

from __future__ import annotations

from croissant_duckdb.naming import name_of
from croissant_duckdb.results import Skipped


def quote(identifier: str) -> str:
    """Quotes a SQL identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def literal(value: str) -> str:
    """Quotes a SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def select_list(record_set, detected: set[str], location: str) -> str | Skipped:
    """The select list renaming the file's columns to the field names, or why it can't be built.

    Args:
        record_set: The record set, whose fields are `column` extracts.
        detected: The columns of the file.
        location: The file, for the reason.
    """
    columns, used = [], {}
    for field in record_set.fields:
        name = name_of(field)
        # DuckDB compares identifiers case-insensitively, and would rename a duplicate to name_1.
        if name.lower() in used:
            return Skipped(f"two fields are named {used[name.lower()]!r} and {name!r}")
        used[name.lower()] = name
        column = field.source.extract.column
        if column not in detected:
            column = column.strip()  # DuckDB strips spaces around CSV headers
        if column not in detected:
            return Skipped(f"column {column!r} not found in {location}")
        columns.append(quote(column) if column == name else f"{quote(column)} AS {quote(name)}")
    return ", ".join(columns)
