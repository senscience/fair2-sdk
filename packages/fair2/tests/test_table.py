import sys

import duckdb

import fair2
from fair2 import Kind


def test_numbers_and_text():
    result = fair2.table(
        duckdb.sql(
            "SELECT * FROM (VALUES ('a<b', 1234567, 0.7400, NULL), ('c', 2, 12.0, 1.5))"
            " t(name, n, score, ratio)"
        ),
        interactive=False,
    )
    assert [(c.name, c.kind) for c in result.columns] == [
        ("name", Kind.TEXT),
        ("n", Kind.INTEGER),
        ("score", Kind.NUMBER),
        ("ratio", Kind.NUMBER),
    ]
    html = result.html()
    assert "a&lt;b" in html and "a<b" not in html  # escaped
    assert ">1,234,567<" in html
    assert ">0.74<" in html and ">12<" in html and ">1.5<" in html
    assert '<td class="text" style="text-align: left">a&lt;b</td>' in html
    assert not result.truncated and "first" not in html
    assert result.interactive is None and "<script" not in html


def test_dates_times_and_other_values_as_text():
    result = fair2.table(
        duckdb.sql(
            "SELECT DATE '2024-03-05' AS d, TIMESTAMP '2024-03-05 14:30:00' AS ts,"
            " TIMESTAMPTZ '2024-03-05 14:30:00+00' AS tz, TIME '14:30:00' AS t, true AS b,"
            " [1, 2] AS l"
        ),
        interactive=False,
    )
    assert [c.kind for c in result.columns] == [
        Kind.DATE,
        Kind.TIMESTAMP,
        Kind.TIMESTAMP,
        Kind.TIME,
        Kind.BOOLEAN,
        Kind.TEXT,
    ]
    # In ISO format, as DuckDB writes them (a time zone needs no pytz this way)
    (row,) = result.rows
    assert row[:2] == ("2024-03-05", "2024-03-05 14:30:00") and row[2].startswith("2024-03-05 ")
    assert row[3:] == ("14:30:00", True, "[1, 2]")
    assert '<td class="date" style="text-align: right">2024-03-05</td>' in result.html()


def test_units_in_the_headers(db):
    units = fair2.units(db)
    # Placeholder units (Unitless, Unknown) aren't units
    assert units == {"age": "a"}
    result = fair2.table(
        db.sql('SELECT participant_id, age, age * 12 AS months FROM "participants"'),
        units=units,
        interactive=False,
    )
    assert [c.label for c in result.columns] == ["participant_id", "age (a)", "months"]
    assert '<span class="unit">(a)</span>' in result.html()
    assert fair2.units(db, "scores") == {}


def test_only_the_first_rows():
    result = fair2.table(duckdb.sql("SELECT range AS i FROM range(10)"), limit=3, interactive=False)
    assert [row[0] for row in result.rows] == [0, 1, 2]
    assert result.truncated
    assert "The first 3 rows." in result._repr_html_()
    assert repr(result) == "<Table: 3 rows (truncated), columns i>"


def test_interactive_with_itables():
    result = fair2.table(
        duckdb.sql(
            "SELECT range AS i, 'x' || range AS s, DATE '2024-01-01' + range::INT AS d"
            " FROM range(30)"
        ),
        units={"i": "kg"},
        limit=5,
    )
    html = result.html()
    # The ITables table, with all the rows, then the plain one with the first rows, which the
    # script removes where scripts run
    assert result.interactive and "dt_for_itables" in html
    assert html.index(result.interactive[:40]) < html.index('class="fair2-table-plain"')
    assert f'document.getElementById("{result.id}")' in html
    assert "The first 5 rows." in html
    # Integers formatted in the browser, for display only; headers with their units; dates as text
    assert "toLocaleString" in html
    assert "i (kg)" in result.interactive
    assert "2024-01-30" in result.interactive
    # The alignment of each column: the text on the left, the numbers and dates on the right
    assert '{"className": "dt-left", "targets": [1]}' in result.interactive
    assert '{"className": "dt-right", "targets": [0, 2]}' in result.interactive


def test_without_itables(monkeypatch):
    monkeypatch.setitem(sys.modules, "itables", None)  # as if it wasn't installed
    result = fair2.table(duckdb.sql("SELECT 1 AS i"))
    assert result.interactive is None and "<script" not in result.html()
