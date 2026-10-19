from helpers import records, rows, types, values


def test_text_fields_keep_leading_zeros(db):
    assert values(db, "SELECT person_id FROM people ORDER BY age") == ["100", "007", "042"]


def test_fields_are_read_with_their_declared_types(db):
    assert types(db.table("measures")) == {
        "code": "VARCHAR",
        "score": "DOUBLE",
        "ok": "BOOLEAN",
        "day": "DATE",
        "at": "TIMESTAMP",
        "small": "INTEGER",
    }
    assert types(db.table("people"))["age"] == "BIGINT"
    assert db.sql("SELECT code, score, ok FROM measures ORDER BY code").fetchall() == [
        ("001", 1.5, True),
        ("002", 2.0, False),
    ]


def test_values_not_matching_the_declared_types_are_reported(db):
    assert db.skipped["mismatch"].startswith("values don't match the declared types in ")
    assert db.skipped["mismatch"].endswith(
        """Error when converting column "count". Could not convert string "NA" to 'BIGINT'"""
    )


def test_missing_columns_are_reported(db):
    assert "column 'no_text' not found" in db.skipped["bad_csv_text"]
    assert "column 'no_number' not found" in db.skipped["bad_csv_number"]


def test_same_values_as_mlcroissant_records_except_lost_leading_zeros(db):
    actual, expected = rows(db, "people"), records(db, "people")
    # mlcroissant reads the CSV with pandas, which parses "007" as a number before converting it
    # back to text: the leading zeros are lost. DuckDB reads the text fields as text.
    assert [r["person_id"] for r in expected] == ["7", "42", "100"]
    assert [r["person_id"] for r in actual] == ["007", "042", "100"]

    def without_id(records):
        return [{k: v for k, v in record.items() if k != "person_id"} for record in records]

    assert without_id(actual) == without_id(expected)
