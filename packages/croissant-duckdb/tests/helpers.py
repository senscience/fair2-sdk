"""Helpers shared by the tests."""

import math


def values(db, query):
    """The values of the first column of a query, as a list."""
    return [row[0] for row in db.sql(query).fetchall()]


def kinds(db):
    """Table name -> "table" or "view"."""
    tables = {name: "table" for name in values(db, "SELECT table_name FROM duckdb_tables()")}
    views = {
        name: "view"
        for name in values(db, "SELECT view_name FROM duckdb_views() WHERE NOT internal")
    }
    return {**tables, **views}


def types(relation):
    """Column name -> DuckDB type of a relation."""
    return dict(zip(relation.columns, map(str, relation.types), strict=True))


def normalize(value):
    if isinstance(value, bytes):
        value = value.decode()
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return (
        float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
    )


def records(db, record_set):
    """The records of a record set read by mlcroissant, keyed by field name."""
    fields = {
        field.id: field.name
        for rs in db.metadata.record_sets
        if rs.id == record_set
        for field in rs.fields
    }
    return [
        {fields[k]: normalize(v) for k, v in record.items()}
        for record in db.dataset.records(record_set=record_set)
    ]


def rows(db, record_set):
    """The rows of a record set's table, keyed by column name."""
    relation = db.table(record_set)
    return [
        dict(zip(relation.columns, map(normalize, row), strict=True)) for row in relation.fetchall()
    ]
