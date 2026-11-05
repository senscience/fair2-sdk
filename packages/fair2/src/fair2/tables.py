"""The result of a DuckDB query as a table, for notebooks.

    fair2.table(con.sql("SELECT gene, count(*) AS n FROM variants GROUP BY gene"))
    fair2.table(db.sql('SELECT age, weight FROM "participants"'), units=fair2.units(db))

Each column has a kind, from its DuckDB type: numbers (integers with thousands separators), and
dates and times in ISO format, are right-aligned; the other values are text. With `units`,
the header of a column gives its unit. With the `tables` extra (ITables), the table can be sorted
by its columns, searched and paged, in the browser: no kernel is needed. DataTables, the JavaScript
of ITables, is loaded from a CDN when the notebook is opened. Where scripts don't run (GitHub,
untrusted notebooks), and without ITables, it is a plain HTML table of the first rows (`limit`).
The template (`templates/table.html.j2`) is autoescaped.
"""

from __future__ import annotations

import dataclasses
import decimal
import enum
import functools
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import duckdb
import jinja2
from markupsafe import Markup

from croissant_duckdb import quote
from fair2.card import NO_UNITS, _first, _texts

if TYPE_CHECKING:
    from croissant_duckdb import Database


class Kind(enum.StrEnum):
    """How the values of a column are shown."""

    INTEGER = "integer"
    NUMBER = "number"
    DATE = "date"
    TIMESTAMP = "timestamp"
    TIME = "time"
    BOOLEAN = "boolean"
    TEXT = "text"


# DuckDB types (the name before any parameters, e.g. DECIMAL(18,3)) -> kind; the others are text.
KINDS = {
    **dict.fromkeys(
        ["TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT"]
        + ["UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT"],
        Kind.INTEGER,
    ),
    **dict.fromkeys(["FLOAT", "DOUBLE", "DECIMAL"], Kind.NUMBER),
    "DATE": Kind.DATE,
    **dict.fromkeys(
        ["TIMESTAMP", "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP_NS", "TIMESTAMP WITH TIME ZONE"],
        Kind.TIMESTAMP,
    ),
    **dict.fromkeys(["TIME", "TIME WITH TIME ZONE"], Kind.TIME),
    "BOOLEAN": Kind.BOOLEAN,
}


@dataclasses.dataclass(frozen=True)
class Column:
    name: str
    kind: Kind
    unit: str | None = None

    @property
    def label(self) -> str:
        """The header: the name, and the unit if there is one."""
        return f"{self.name} ({self.unit})" if self.unit else self.name

    @property
    def numeric(self) -> bool:
        return self.kind in (Kind.INTEGER, Kind.NUMBER)

    @property
    def align(self) -> str:
        """Numbers, dates and times on the right, as DataTables does; the rest on the left."""
        return "left" if self.kind in (Kind.BOOLEAN, Kind.TEXT) else "right"


@dataclasses.dataclass(frozen=True)
class Table:
    columns: list[Column]
    rows: list[tuple]
    """The rows of the plain table: dates, times and other non-numeric values as text."""
    truncated: bool
    """Whether the result has more rows than shown."""
    interactive: str | None = None
    """The HTML of the ITables table, when ITables is installed."""
    id: str = dataclasses.field(
        default_factory=lambda: f"fair2-table-{uuid.uuid4().hex[:12]}", compare=False
    )
    """The id of its HTML element: unique, for its script to find it in the notebook."""

    def html(self) -> str:
        return _template().render(table=self, interactive=Markup(self.interactive or ""))

    def _repr_html_(self) -> str:
        return self.html()

    def __repr__(self) -> str:
        more = " (truncated)" if self.truncated else ""
        names = ", ".join(column.label for column in self.columns)
        return f"<Table: {len(self.rows)} rows{more}, columns {names}>"


def table(
    relation: duckdb.DuckDBPyRelation,
    *,
    units: Mapping[str, str] | None = None,
    limit: int = 100,
    interactive: bool = True,
    max_rows: int = 10_000,
    page_length: int = 20,
) -> Table:
    """A query result, displayed as a table by Jupyter.

    Args:
        units: Column name -> unit, shown in its header: e.g. `fair2.units(db)`.
        limit: The rows of the plain table.
        interactive: Whether to sort, search and page it with ITables, when installed.
        max_rows: The rows of the interactive table: they are all in the notebook.
        page_length: The rows of a page of the interactive table.
    """
    units = units or {}
    columns = [
        Column(name, KINDS.get(str(t).split("(")[0], Kind.TEXT), units.get(name))
        for name, t in zip(relation.columns, relation.types, strict=True)
    ]
    # Numbers and booleans as they are, the rest as DuckDB writes it: ISO dates and times, lists...
    # (Python can't fetch timestamps with a time zone without pytz.) Named by their header.
    shown = relation.project(
        ", ".join(
            f"{quote(c.name)}{'' if c.numeric or c.kind == Kind.BOOLEAN else '::VARCHAR'}"
            f" AS {quote(c.label)}"
            for c in columns
        )
    )
    rows = shown.limit(limit + 1).fetchall()
    datatable = _datatable(shown, columns, max_rows, page_length) if interactive else None
    return Table(columns, rows[:limit], len(rows) > limit, datatable)


def units(db: Database, record_set: str | None = None) -> dict[str, str]:
    """The units of the fields in the metadata, by field name: for the headers of `table()`.

    Args:
        record_set: Only the fields of this record set (@id or name). Otherwise those of all the
            record sets, except the names that don't have the same unit in all of them.
    """
    found: dict[str, set[str | None]] = {}
    for rs in db.metadata.record_sets:
        if record_set is not None and record_set not in (rs.id, rs.name):
            continue
        for field in rs.fields:
            unit = _unit((field.extra_properties or {}).get("unit"))
            found.setdefault(field.name, set()).add(unit)
    return {name: next(iter(u)) for name, u in found.items() if len(u) == 1 and None not in u}


def _unit(value: Any) -> str | None:
    """A unit as shown in a header: its symbol ("s"), or its label without one ("Ratio").

    Placeholder units (QUDT's "Unknown" and "Unitless", given to text fields) aren't shown.
    """
    if isinstance(value, dict):
        label = (value.get("label") or "").strip()
        symbol = (value.get("symbol") or "").strip()
        if label.lower() in NO_UNITS:
            return None
        return symbol if symbol and symbol.lower() not in NO_UNITS else label or None
    return _first(_texts(value))


def _datatable(
    shown: duckdb.DuckDBPyRelation, columns: list[Column], max_rows: int, page_length: int
) -> str | None:
    """The HTML of the table with ITables, or None without it."""
    try:
        import itables
    except ImportError:
        return None
    # Integers shown with thousands separators; sorting and searching use the numbers.
    render = itables.JavascriptFunction(
        "function (data, type) { return type === 'display' && data !== null"
        " ? Number(data).toLocaleString('en-US') : data; }"
    )
    integers = [i for i, column in enumerate(columns) if column.kind == Kind.INTEGER]
    # The alignment of each column, rather than the one of the types DataTables detects
    aligned = {
        align: [i for i, column in enumerate(columns) if column.align == align]
        for align in ("left", "right")
    }
    column_defs = [
        {"targets": targets, "className": f"dt-{align}"}
        for align, targets in aligned.items()
        if targets
    ]
    if integers:
        column_defs.append({"targets": integers, "render": render})
    return itables.to_html_datatable(
        shown.limit(max_rows).df(),
        connected=True,
        showIndex=False,
        display_logo_when_loading=False,
        pageLength=page_length,
        lengthMenu=sorted({10, page_length, 50, 100}),
        # All the rows given, not a sample of them.
        maxBytes=0,
        columnDefs=column_defs,
        classes="display compact",
    )


def _cell(value: Any) -> str:
    """A value as shown in a cell: integers with thousands separators, up to 4 decimals."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float | decimal.Decimal):
        if value == int(value) and abs(value) < 1e15:
            return f"{int(value):,}"
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return str(value)


@functools.cache
def _template() -> jinja2.Template:
    environment = jinja2.Environment(
        loader=jinja2.PackageLoader("fair2", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=jinja2.StrictUndefined,
    )
    environment.filters["cell"] = _cell
    return environment.get_template("table.html.j2")
