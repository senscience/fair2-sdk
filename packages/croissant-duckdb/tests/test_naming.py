def test_columns_are_renamed_to_field_names(db):
    assert db.table("scores").columns == ["score_id", "label", "score"]
    assert db.table("people").columns == ["person_id", "name", "age"]


def test_names_are_used_as_they_are(db):
    assert db.tables["labelled"] == "Scores (labelled)"
    assert db.table("Scores (labelled)").columns == ["Score (0-1)"]
    assert db.sql('SELECT max("Score (0-1)") FROM "Scores (labelled)"').fetchone()[0] is not None


def test_record_sets_and_fields_without_name_use_the_suffix_of_their_id(db):
    assert db.tables["unnamed"] == "unnamed"
    assert db.table("unnamed").columns == ["id"]  # field @id "unnamed/id"


def test_names_conflicting_for_duckdb_are_skipped(db):
    # DuckDB compares names case-insensitively.
    assert (
        db.skipped["scores_again"] == "table name 'SCORES' is already used by record set 'scores'"
    )
    assert db.skipped["twice"] == "two fields are named 'label' and 'LABEL'"
