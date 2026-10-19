"""CSV and TSV files are loaded into tables, with the types declared by the fields.

They can't be read partially, so each file is downloaded once into DuckDB's columnar storage. Fields
are read with their declared types (sc:Integer as BIGINT, sc:Date as DATE...): that's how DuckDB
parses the file, not a cast. Text fields are read as text, so identifiers keep their leading zeros.
A file whose values don't match the declared types is skipped with the reason.
"""

from __future__ import annotations

import re

import duckdb

from croissant_duckdb.results import Registered, Registration, Skipped
from croissant_duckdb.sql import literal, quote, select_list

ENCODING_FORMATS = ("text/csv", "text/tab-separated-values")

# DuckDB types for the Croissant atomic data types. Other data types (semantic types, e.g.
# sc:GeoCoordinates) keep the type DuckDB detects.
DUCKDB_TYPES = {
    "Text": "VARCHAR",
    "Integer": "BIGINT",
    "Float": "DOUBLE",
    "Boolean": "BOOLEAN",
    "Date": "DATE",
    "DateTime": "TIMESTAMP",
    "Time": "TIME",
    "Int8": "TINYINT",
    "Int16": "SMALLINT",
    "Int32": "INTEGER",
    "Int64": "BIGINT",
    "UInt8": "UTINYINT",
    "UInt16": "USMALLINT",
    "UInt32": "UINTEGER",
    "UInt64": "UBIGINT",
    "Float16": "FLOAT",
    "Float32": "FLOAT",
    "Float64": "DOUBLE",
}


def duckdb_type(field) -> str | None:
    """The DuckDB type of a field's first atomic data type (sc:Integer, cr:Int32...), or None."""
    for data_type in field.data_types:
        local_name = re.split(r"[/:#]", str(data_type))[-1]
        if local_name in DUCKDB_TYPES:
            return DUCKDB_TYPES[local_name]
    return None


def register(con, record_set, location: str, name: str) -> Registration:
    """Loads a CSV file into a table, downloading it once.

    The file is loaded into a temporary table, whose columns are then checked and renamed: asking
    DuckDB for the columns first (DESCRIBE) would download the whole file twice more.
    """
    url = literal(location)
    # DuckDB strips spaces around CSV headers.
    declared = {
        field.source.extract.column.strip(): duckdb_type(field) for field in record_set.fields
    }
    declared = {column: type_ for column, type_ in declared.items() if type_}
    types = ""
    if declared:
        pairs = (f"{literal(column)}: {literal(type_)}" for column, type_ in declared.items())
        types = ", types = {" + ", ".join(pairs) + "}"
    raw = quote(f"{name}__file")
    try:
        con.sql(f"CREATE OR REPLACE TEMP TABLE {raw} AS FROM read_csv({url}{types})")
    except duckdb.Error as e:
        message = str(e)
        error = message.splitlines()[0]
        if not types:
            return Skipped(f"can't read {location}: {error}")
        # Either a declared column is missing from the file, or a value doesn't match its declared
        # type (e.g. "NA" in an Integer column): read without types to tell which.
        try:
            con.sql(f"CREATE OR REPLACE TEMP TABLE {raw} AS FROM read_csv({url})")
        except duckdb.Error:
            return Skipped(f"can't read {location}: {error}")
        try:
            columns = select_list(record_set, set(con.sql(f"FROM {raw}").columns), location)
            if isinstance(columns, Skipped):
                return columns
            # The "Error when converting column ..." line of DuckDB's message names the column and
            # the value.
            details = next(
                (line for line in message.splitlines() if line.startswith("Error when converting")),
                error,
            )
            return Skipped(f"values don't match the declared types in {location}: {details}")
        finally:
            con.sql(f"DROP TABLE IF EXISTS {raw}")
    try:
        columns = select_list(record_set, set(con.sql(f"FROM {raw}").columns), location)
        if isinstance(columns, Skipped):
            return columns
        con.sql(f"CREATE OR REPLACE TABLE {quote(name)} AS SELECT {columns} FROM {raw}")
        return Registered(name)
    finally:
        con.sql(f"DROP TABLE IF EXISTS {raw}")
