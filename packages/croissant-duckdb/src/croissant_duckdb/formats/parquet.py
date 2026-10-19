"""Parquet files become views.

Queries read them remotely with HTTP range requests, fetching only the footer, the columns and the
row groups they need. They keep the types the files store, without casts.
"""

from __future__ import annotations

import duckdb

from croissant_duckdb.results import Registered, Registration, Skipped
from croissant_duckdb.sql import literal, quote, select_list

ENCODING_FORMATS = ("application/x-parquet", "application/vnd.apache.parquet")


def register(con, record_set, location: str, name: str) -> Registration:
    """Creates the view of a record set."""
    url = literal(location)
    try:
        # Only reads the Parquet footer.
        description = con.sql(f"DESCRIBE SELECT * FROM read_parquet({url})").fetchall()
    except duckdb.Error as e:
        return Skipped(f"can't read {location}: {str(e).splitlines()[0]}")
    columns = select_list(record_set, {row[0] for row in description}, location)
    if isinstance(columns, Skipped):
        return columns
    con.sql(f"CREATE OR REPLACE VIEW {quote(name)} AS SELECT {columns} FROM read_parquet({url})")
    return Registered(name)
