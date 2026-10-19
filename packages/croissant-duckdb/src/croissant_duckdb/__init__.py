"""Expose the record sets of a Croissant dataset as DuckDB tables and views.

import croissant_duckdb

db = croissant_duckdb.connect("https://sen.science/doi/10.71728/senscience.k7f3-9xqm/fair2.json")
db.sql("SELECT count(*) FROM sweep_traces").fetchone()
sweep_metadata = db.table("sweep_metadata").df()
"""

from croissant_duckdb.database import Database, TableNotFoundError, connect
from croissant_duckdb.sql import literal, quote

__all__ = ["Database", "TableNotFoundError", "connect", "literal", "quote"]
