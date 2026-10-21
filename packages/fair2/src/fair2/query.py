"""A SQL query box for notebooks: an editor with completion, a Run button, and the result below.

    box = fair2.query_box(db, 'SELECT * FROM "participants" LIMIT 10')
    box  # displayed by Jupyter
    box.result  # the last result, as a pandas DataFrame
    box.export("csv")  # the whole result, as its Download buttons do

The editor is CodeMirror 6 in an anywidget (`static/query_box.js`, built from `js/`). It completes
SQL keywords, the tables and views of the DuckDB connection, and the columns of the tables a query
names. Needs a running kernel (JupyterLab, Notebook 7, VS Code, Colab), and the `widgets` extra:
`pip install fair2[widgets]`.
"""

from __future__ import annotations

import tempfile
from html import escape
from importlib import resources
from pathlib import Path

import duckdb

from croissant_duckdb import Database, literal
from fair2.html import _size

try:
    import anywidget
    import ipywidgets
    import traitlets
except ImportError as e:  # the widgets extra isn't installed
    raise ImportError(
        "fair2.query_box needs anywidget: install fair2[widgets] (pip install 'fair2[widgets]')"
    ) from e


def schema(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Table and view names -> their column names, in order, from the DuckDB catalog."""
    rows = con.sql("""
        SELECT table_name, column_name FROM duckdb_columns()
        WHERE NOT internal AND schema_name = 'main'
        ORDER BY table_name, column_index
    """).fetchall()
    tables: dict[str, list[str]] = {}
    for table, column in rows:
        tables.setdefault(table, []).append(column)
    return tables


def run(con: duckdb.DuckDBPyConnection, query: str, limit: int):
    """Runs a query: (DataFrame of at most `limit` rows, or None, and a message for the reader).

    Statements without a result (CREATE, INSERT...) return None and "Done.". Only `limit` + 1 rows
    are fetched, to tell whether there are more.
    """
    relation = con.sql(query)
    if relation is None:
        return None, "Done."
    frame = relation.limit(limit + 1).df()
    if len(frame) > limit:
        return frame.head(limit), f"The first {limit:,} rows."
    return frame, f"{len(frame):,} row{'s' if len(frame) != 1 else ''}."


# Export formats: DuckDB COPY options, the MIME type of the download, and the button's label.
FORMATS = {
    "csv": ("FORMAT csv, HEADER", "text/csv", "CSV"),
    "parquet": ("FORMAT parquet", "application/vnd.apache.parquet", "Parquet"),
}

# Above this size, a result is saved next to the notebook instead of being sent to the browser:
# large messages between the kernel and the browser are slow, and frontends limit their size.
MAX_DOWNLOAD_BYTES = 50_000_000


def export(con: duckdb.DuckDBPyConnection, query: str, path: Path, format: str) -> None:
    """Writes the whole result of a query to a file, streamed by DuckDB (not through pandas)."""
    options, _, _ = FORMATS[format]
    # As a subquery: without the semicolon that may end it.
    con.sql(f"COPY ({query.strip().rstrip(';')}) TO {literal(str(path))} ({options})")


def _free_path(folder: Path, name: str) -> Path:
    """`name` in `folder`, or `name-1`, `name-2`... when it is taken: never overwrite a file."""
    path = folder / name
    stem, suffix = path.stem, path.suffix
    count = 1
    while path.exists():
        path = folder / f"{stem}-{count}{suffix}"
        count += 1
    return path


class _Editor(anywidget.AnyWidget):
    _esm = (resources.files("fair2") / "static" / "query_box.js").read_text(encoding="utf-8")
    _css = """
    .fair2-query-bar { display: flex; align-items: center; gap: 0.75em; margin: 0.4em 0; }
    .fair2-query-bar button {
      padding: 0.3em 1.2em; border-radius: 9999px; border: none; cursor: pointer;
      background: var(--jp-brand-color1, #0024b0); color: white; font-weight: 600;
    }
    .fair2-query-bar span { color: var(--jp-ui-font-color2, #6b6a66); font-size: 0.85em; }
    """
    query = traitlets.Unicode("").tag(sync=True)
    schema = traitlets.Dict().tag(sync=True)


class QueryBox(ipywidgets.VBox):
    """The editor, the export of the result, and the output where the result is shown."""

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        query: str = "",
        limit: int = 100,
        max_download_bytes: int = MAX_DOWNLOAD_BYTES,
    ):
        self._con = con
        self._limit = limit
        self._max_download_bytes = max_download_bytes
        self._editor = _Editor(query=query, schema=schema(con))
        self._output = ipywidgets.Output()
        self.result = None
        """The DataFrame of the last query run, or None."""
        self._ran = None
        """The last query run with a result: what the export writes."""
        self._editor.on_msg(self._on_message)

        # The export, shown once a query has a result.
        self._name = ipywidgets.Text(
            value="query-result", description="File", layout=ipywidgets.Layout(width="18em")
        )
        buttons = []
        for format, (_, _, label) in FORMATS.items():
            button = ipywidgets.Button(
                description=f"Download {label}",
                icon="download",
                layout=ipywidgets.Layout(width="auto"),
            )
            button.on_click(lambda _, format=format: self.export(format))
            buttons.append(button)
        self._status = ipywidgets.HTML()
        self._export = ipywidgets.HBox(
            [self._name, *buttons, self._status], layout=ipywidgets.Layout(display="none")
        )
        super().__init__([self._editor, self._export, self._output])

    @property
    def query(self) -> str:
        return self._editor.query

    def _repr_mimebundle_(self, **kwargs):
        # Shown where widgets can't be (no kernel, a front-end without them): how to query instead.
        bundle = super()._repr_mimebundle_(**kwargs)
        bundle["text/plain"] = (
            "SQL editor (needs a running notebook with widgets). Without it, run queries in a cell:"
            f" con.sql({self.query!r}).df()"
        )
        return bundle

    def run(self) -> None:
        """Runs the query of the editor, as its Run button does."""
        self._output.clear_output()
        self._status.value = ""
        query = self.query
        try:
            self.result, message = run(self._con, query, self._limit)
        except duckdb.Error as e:
            # DuckDB's message says what is wrong, and where: no Python traceback.
            self.result = None
            self._ran = None
            self._export.layout.display = "none"
            self._output.append_stdout(f"{e}\n")
            return
        self._ran = query if self.result is not None else None
        self._export.layout.display = "flex" if self._ran else "none"
        if self.result is not None:
            self._output.append_display_data(self.result)
        self._output.append_stdout(f"{message}\n")
        # A query can create tables: complete them too.
        self._editor.schema = schema(self._con)

    def export(self, format: str) -> Path | None:
        """Exports the whole result of the last query run (not only the rows shown).

        Up to `max_download_bytes`, the file is sent to the browser, which downloads it. Larger, it
        is saved next to the notebook (the working directory), without overwriting a file, and
        its path is returned.

        Args:
            format: "csv" or "parquet".
        """
        if self._ran is None:
            self._status.value = "Run a query with a result first."
            return None
        name = f"{Path(self._name.value.strip() or 'query-result').name}.{format}"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            try:
                export(self._con, self._ran, path, format)
            except duckdb.Error as e:
                self._status.value = f"Export failed: {escape(str(e).splitlines()[0])}"
                return None
            size = path.stat().st_size
            if size <= self._max_download_bytes:
                _, mime, _ = FORMATS[format]
                self._editor.send(
                    {"type": "download", "name": name, "mime": mime}, buffers=[path.read_bytes()]
                )
                self._status.value = f"Downloaded {escape(name)} ({_size(size)})."
                return None
            saved = _free_path(Path.cwd(), name)
            path.replace(saved)
        self._status.value = (
            f"Saved to <code>{escape(str(saved))}</code> ({_size(size)}): too large to download"
            " from here. Download it from the file browser."
        )
        return saved

    def _on_message(self, _widget, content, _buffers) -> None:
        if content.get("type") == "run":
            self.run()


def query_box(
    source: Database | duckdb.DuckDBPyConnection,
    query: str = "",
    *,
    limit: int = 100,
    max_download_bytes: int = MAX_DOWNLOAD_BYTES,
):
    """A SQL editor with completion, a Run button, and the export of the result.

    Args:
        source: A `croissant_duckdb.Database`, or a DuckDB connection.
        query: The query the editor starts with.
        limit: The number of rows shown. The export has them all.
        max_download_bytes: Larger exports are saved next to the notebook instead of downloaded.
    """
    con = source.con if isinstance(source, Database) else source
    return QueryBox(con, query, limit, max_download_bytes)
