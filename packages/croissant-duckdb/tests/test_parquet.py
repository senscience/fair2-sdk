from helpers import records, rows, types


def test_types_come_from_the_files(db):
    assert types(db.table("scores")) == {
        "score_id": "INTEGER",
        "label": "VARCHAR",
        "score": "DECIMAL(2,1)",
    }


def test_unreadable_files_and_missing_columns_are_reported(db):
    assert "can't read" in db.skipped["missing"]
    assert "column 'does_not_exist' not found" in db.skipped["bad_column"]


def test_same_values_as_mlcroissant_records(db):
    assert rows(db, "scores") == records(db, "scores")
