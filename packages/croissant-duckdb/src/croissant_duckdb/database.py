"""DuckDB tables and views for the record sets of a Croissant dataset.

Supported record sets: every field is a `column` extract from the same `FileObject`, in a format of
`croissant_duckdb.formats` (CSV, TSV, Parquet), without transforms or sub-fields. Other record sets
are listed in `Database.skipped` with the reason, and can still be read with
`mlcroissant.Dataset.records()`.

- CSV and TSV files are loaded into tables, with the declared types (`formats.csv`).
- Parquet files become views, read remotely (`formats.parquet`).
- Tables and columns are named after the record sets and fields (`naming`).
"""

from __future__ import annotations

import dataclasses
import re
from concurrent.futures import ThreadPoolExecutor

import duckdb
import mlcroissant as mlc

from croissant_duckdb.formats import reader_for
from croissant_duckdb.naming import assign_table_names
from croissant_duckdb.results import Registered, Skipped
from croissant_duckdb.sql import quote


class TableNotFoundError(KeyError):
    """Raised when a record set has no table: it doesn't exist, or it was skipped.

    A subclass of KeyError, so that code catching KeyError still works.

    Attributes:
        record_set: The @id, name or table name that was looked up.
        reason: Why the record set was skipped, or None if there is no such record set.
    """

    def __init__(self, record_set: str, reason: str | None, tables: list[str]):
        self.record_set = record_set
        self.reason = reason
        if reason:
            message = f"Record set {record_set!r} has no table: {reason}"
        else:
            message = f"Unknown record set {record_set!r}. Tables: {sorted(tables)}"
        super().__init__(message)

    def __str__(self) -> str:
        # KeyError shows its message as a repr, in quotes: show it as is.
        return self.args[0]


@dataclasses.dataclass
class Database:
    """A DuckDB connection with one table or view per supported record set."""

    con: duckdb.DuckDBPyConnection
    dataset: mlc.Dataset
    tables: dict[str, str]
    """Record set @id -> name of its DuckDB table or view."""
    skipped: dict[str, str]
    """Record set @id -> reason why it has no table."""

    @property
    def metadata(self) -> mlc.Metadata:
        return self.dataset.metadata

    def sql(self, query: str, **kwargs) -> duckdb.DuckDBPyRelation:
        """Runs a SQL query on the connection."""
        return self.con.sql(query, **kwargs)

    def table(self, record_set: str) -> duckdb.DuckDBPyRelation:
        """Returns the table of a record set, given its @id, its name or its table name.

        Raises:
            TableNotFoundError: The record set doesn't exist, or it was skipped (see `skipped`).
        """
        return self.con.sql(f"FROM {quote(self._resolve_table(record_set))}")

    def _resolve_table(self, record_set: str) -> str:
        """Returns the table name of a record set, given its @id, its name or its table name.

        Raises:
            TableNotFoundError: The record set doesn't exist, or it was skipped (see `skipped`).
        """
        if record_set in self.tables:
            return self.tables[record_set]
        if record_set in self.tables.values():
            return record_set
        for rs in self.metadata.record_sets:
            if rs.name == record_set and rs.id in self.tables:
                return self.tables[rs.id]
        reason = self.skipped.get(record_set) or next(
            (
                self.skipped[rs.id]
                for rs in self.metadata.record_sets
                if rs.name == record_set and rs.id in self.skipped
            ),
            None,
        )
        raise TableNotFoundError(record_set, reason, list(self.tables.values()))


def connect(
    source: str | mlc.Dataset,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    max_workers: int = 8,
    verbose: bool = True,
) -> Database:
    """Reads a Croissant dataset and creates one DuckDB table or view per supported record set.

    Args:
        source: URL or path of the Croissant JSON-LD file, or an `mlcroissant.Dataset`.
        con: DuckDB connection to use. A new in-memory one by default.
        max_workers: Number of files read in parallel.
        verbose: Print the record sets that are skipped.
    """
    dataset = source if isinstance(source, mlc.Dataset) else mlc.Dataset(source)
    con = con if con is not None else duckdb.connect()
    file_objects = {fo.id: fo for fo in dataset.metadata.distribution}

    readable, skipped = [], {}
    for record_set in dataset.metadata.record_sets:
        match _file_object(record_set, file_objects):
            case Skipped(reason):
                skipped[record_set.id] = reason
            case file_object:
                readable.append((record_set, file_object))
    # Names are only given to readable record sets: one that can't be read doesn't take a name.
    names, name_conflicts = assign_table_names([record_set for record_set, _ in readable])
    skipped.update(name_conflicts)
    supported = [(record_set, fo) for record_set, fo in readable if record_set.id in names]

    if any(fo.content_url.startswith(("http://", "https://")) for _, fo in supported):
        # httpfs reads files over HTTP(S), fetching only the byte ranges a query needs.
        con.install_extension("httpfs")
        con.load_extension("httpfs")
        # Published files don't change: cache their HTTP metadata (size, modification date).
        con.sql("SET enable_http_metadata_cache = true")

    folder = dataset.metadata.ctx.folder

    def register(args):
        record_set, file_object = args
        # Each thread needs its own cursor on the connection.
        location = _location(file_object.content_url, folder)
        reader = reader_for(file_object.encoding_formats)
        return reader.register(con.cursor(), record_set, location, names[record_set.id])

    tables = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(register, supported)
        for (record_set, _), result in zip(supported, results, strict=True):
            match result:
                case Registered(table):
                    tables[record_set.id] = table
                case Skipped(reason):
                    skipped[record_set.id] = reason

    if verbose:
        for record_set_id, reason in skipped.items():
            print(f"Skipping record set {record_set_id}: {reason}")
    return Database(con=con, dataset=dataset, tables=tables, skipped=skipped)


def _file_object(record_set, file_objects) -> mlc.FileObject | Skipped:
    """The FileObject of a record set made of plain columns, in a supported format, or why not."""
    if not record_set.fields:
        return Skipped("no fields")
    sources = {field.source.file_object for field in record_set.fields}
    if len(sources) != 1 or None in sources:
        return Skipped("fields don't come from a single FileObject")
    for field in record_set.fields:
        if field.sub_fields or field.source.transforms or not field.source.extract.column:
            return Skipped(f"field {field.name!r} isn't a plain column")
    file_object = file_objects.get(sources.pop())
    if file_object is None or not getattr(file_object, "content_url", None):
        return Skipped("source isn't a FileObject with a contentUrl")
    if file_object.contained_in:
        return Skipped("file is inside an archive")
    if reader_for(file_object.encoding_formats) is None:
        return Skipped(f"unsupported format {file_object.encoding_formats}")
    return file_object


def _location(content_url: str, folder) -> str:
    """URLs are kept; relative paths are resolved against the folder of the Croissant file."""
    if re.match(r"^[a-z][a-z0-9+.-]*://", content_url) or folder is None:
        return content_url
    return str(folder / content_url)
