"""One module per file format, each with the same interface.

- `ENCODING_FORMATS`: the encoding formats (MIME types) the module reads.
- `register(con, record_set, location, name)`: creates the table or view of a record set on the
  cursor `con`, and returns `Registered(table)`, or `Skipped(reason)` when the file can't be read.
"""

from __future__ import annotations

from types import ModuleType

from croissant_duckdb.formats import csv, parquet

FORMATS: dict[str, ModuleType] = {
    encoding_format: module
    for module in (csv, parquet)
    for encoding_format in module.ENCODING_FORMATS
}


def reader_for(encoding_formats) -> ModuleType | None:
    """The module reading the first supported encoding format, or None."""
    return next((FORMATS[f] for f in encoding_formats or [] if f in FORMATS), None)
