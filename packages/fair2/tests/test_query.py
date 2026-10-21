import fair2
from fair2 import query


def test_schema_has_tables_views_and_columns_in_order(db):
    tables = query.schema(db.con)
    assert tables["participants"] == ["participant_id", "age", "site", "visit"]
    # Parquet files are views: their columns are completed too.
    assert tables["scores"] == ["score_id", "score"]


def test_run_limits_the_rows(db):
    frame, message = query.run(db.con, "SELECT * FROM range(10)", limit=3)
    assert len(frame) == 3
    assert message == "The first 3 rows."
    frame, message = query.run(db.con, "SELECT 1 AS x", limit=3)
    assert frame.x.tolist() == [1]
    assert message == "1 row."


def test_statements_without_result(db):
    frame, message = query.run(db.con, "CREATE TABLE t AS SELECT 1 AS x", limit=3)
    assert frame is None
    assert message == "Done."


def test_the_box_runs_its_query_and_completes_new_tables(db):
    box = fair2.query_box(db, "SELECT count(*) AS n FROM participants")
    assert box.query == "SELECT count(*) AS n FROM participants"
    box.run()
    assert box.result.n.tolist() == [4]
    # A query creating a table: the editor completes it afterwards.
    box._editor.query = "CREATE TABLE adults AS SELECT * FROM participants WHERE age >= 30"
    box.run()
    assert "adults" in box._editor.schema


def test_without_widgets_the_text_says_how_to_query(db):
    bundle = fair2.query_box(db, "SELECT 1")._repr_mimebundle_()
    assert "application/vnd.jupyter.widget-view+json" in bundle
    assert bundle["text/plain"].endswith("con.sql('SELECT 1').df()")


def test_errors_are_shown_not_raised(db):
    box = fair2.query_box(db, "SELECT * FROM nothing")
    box.run()
    assert box.result is None
    assert "Table with name nothing does not exist" in box._output.outputs[0]["text"]


def test_the_result_is_shown_with_the_number_of_rows(db):
    box = fair2.query_box(db, "SELECT * FROM participants", limit=2)
    box.run()
    table, message = box._output.outputs
    assert "text/html" in table["data"]
    assert message["text"] == "The first 2 rows.\n"


def sent(box, monkeypatch):
    """The messages the box sends to the browser: (content, buffers)."""
    messages = []
    monkeypatch.setattr(
        box._editor, "send", lambda content, buffers=None: messages.append((content, buffers))
    )
    return messages


def test_export_downloads_the_whole_result(db, monkeypatch):
    box = fair2.query_box(
        db, "SELECT participant_id, age FROM participants ORDER BY participant_id;", limit=1
    )
    messages = sent(box, monkeypatch)
    box.run()
    assert len(box.result) == 1  # one row shown
    box._name.value = "adults"
    assert box.export("csv") is None
    ((content, buffers),) = messages
    assert content == {"type": "download", "name": "adults.csv", "mime": "text/csv"}
    # All the rows, with the header; leading zeros kept (the CSV field is text).
    assert buffers[0].decode().splitlines() == [
        "participant_id,age",
        "007,36",
        "042,",
        "100,28",
        "101,45",
    ]
    assert box._status.value.startswith("Downloaded adults.csv")


def test_export_to_parquet(db, monkeypatch, tmp_path):
    box = fair2.query_box(db, "SELECT * FROM scores")
    messages = sent(box, monkeypatch)
    box.run()
    box.export("parquet")
    ((content, buffers),) = messages
    assert content["name"] == "query-result.parquet"
    (tmp_path / "scores.parquet").write_bytes(buffers[0])
    assert db.sql(f"SELECT count(*) FROM '{tmp_path / 'scores.parquet'}'").fetchone()[0] == 4


def test_large_exports_are_saved_next_to_the_notebook(db, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "query-result.csv").write_text("already here")
    box = fair2.query_box(db, "SELECT * FROM participants", max_download_bytes=10)
    messages = sent(box, monkeypatch)
    box.run()
    saved = box.export("csv")
    assert messages == []
    # Not over the existing file.
    assert saved == tmp_path / "query-result-1.csv"
    assert saved.read_text().startswith("participant_id,age,site,visit")
    assert (tmp_path / "query-result.csv").read_text() == "already here"
    assert "too large to download" in box._status.value


def test_export_needs_a_result(db, monkeypatch):
    box = fair2.query_box(db, "CREATE TABLE copy AS SELECT * FROM participants")
    messages = sent(box, monkeypatch)
    assert box._export.layout.display == "none"
    box.run()  # no result: no export
    assert box._export.layout.display == "none"
    assert box.export("csv") is None
    assert messages == []
    box._editor.query = "SELECT * FROM copy"
    box.run()
    assert box._export.layout.display == "flex"


def test_export_writes_the_query_that_ran_not_the_edited_one(db, monkeypatch):
    box = fair2.query_box(db, "SELECT 1 AS ran")
    messages = sent(box, monkeypatch)
    box.run()
    box._editor.query = "SELECT 2 AS edited"
    box.export("csv")
    assert messages[0][1][0].decode().splitlines() == ["ran", "1"]
