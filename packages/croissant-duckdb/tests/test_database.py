import mlcroissant as mlc
import pytest

import croissant_duckdb
from helpers import kinds


def test_csv_is_a_table_and_parquet_a_view(db):
    assert kinds(db) == {
        "people": "table",
        "measures": "table",
        "scores": "view",
        "data/items.parquet": "view",
        "dup/items.parquet": "view",
        "Scores (labelled)": "view",
        "unnamed": "view",
    }


def test_skipped_record_sets_have_a_reason(db):
    assert set(db.skipped) == {
        "sheet",
        "missing",
        "bad_column",
        "bad_csv_text",
        "bad_csv_number",
        "scores_again",
        "twice",
        "mismatch",
    }
    assert "unsupported format" in db.skipped["sheet"]


def test_table_lookup(db):
    assert db._resolve_table("people") == "people"  # record set @id
    assert db._resolve_table("labelled") == "Scores (labelled)"  # record set @id
    assert db._resolve_table("Scores (labelled)") == "Scores (labelled)"  # record set name
    with pytest.raises(KeyError, match="has no table: unsupported format"):
        db.table("sheet")
    with pytest.raises(KeyError, match="Unknown record set"):
        db.table("nothing")


def test_missing_tables_raise_a_specific_error(db):
    with pytest.raises(croissant_duckdb.TableNotFoundError) as skipped:
        db.table("sheet")
    assert skipped.value.record_set == "sheet"
    assert skipped.value.reason.startswith("unsupported format")
    assert str(skipped.value).startswith("Record set 'sheet' has no table: unsupported format")
    with pytest.raises(croissant_duckdb.TableNotFoundError) as unknown:
        db.table("nothing")
    assert unknown.value.reason is None
    assert str(unknown.value).startswith("Unknown record set 'nothing'. Tables: [")


def test_accepts_an_mlcroissant_dataset(dataset_path):
    dataset = mlc.Dataset(str(dataset_path))
    db = croissant_duckdb.connect(dataset, verbose=False)
    assert db.dataset is dataset
    assert db.table("people").count("*").fetchone()[0] == 3
