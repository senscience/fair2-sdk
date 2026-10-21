import pytest

import fair2
from fair2.card import ColumnStats


@pytest.fixture
def card(db):
    return fair2.card(db)


def record_set(card, name):
    return next(rs for rs in card.record_sets if rs.name == name)


def field(card, record_set_name, name):
    return next(f for f in record_set(card, record_set_name).fields if f.name == name)


def test_dataset_metadata(card):
    assert card.name == "Test <dataset>"
    assert card.doi == "10.71728/senscience.test-0001"
    assert card.version == "1.2.0"
    assert card.date_published == "2026-05-19"
    assert card.license.text == "CC BY 4.0"
    assert card.authors == ["Ada Lovelace", "Grace Hopper"]
    assert card.cite_as.startswith("Lovelace, A. 2026")
    assert card.data_article.text == "The test article"
    assert card.data_article.url == "https://doi.org/10.3389/test.2026.1"
    # Split on semicolons, without duplicates.
    assert card.keywords == ["memory", "attention", "students"]
    assert card.spatial_coverage == ["Lausanne, Switzerland"]
    assert card.temporal_coverage == ["2024-03/2024-04"]


def test_source_is_the_croissant_file_that_was_read(card, dataset_path):
    # A local path: not a link.
    assert card.source.text == str(dataset_path)
    assert card.source.url is None


def test_responsible_use_merges_rai_and_fair2_properties(card):
    assert dict(card.responsible_use) == {
        "Intended uses": ["Teaching", "Benchmarks"],
        "Limitations": ["Small sample"],
        "Biases": ["Students only", "Recruited in two cities."],
        "Data collection": ["Questionnaires during the first visit."],
    }


def test_record_sets(card):
    participants = record_set(card, "participants")
    assert participants.table == "participants"
    assert participants.file.text == "participants.csv"
    assert participants.format == "CSV"
    assert participants.rows == 4
    assert record_set(card, "scores").format == "Parquet"
    notes = record_set(card, "notes")
    assert notes.table is None
    assert "unsupported format" in notes.skipped
    assert notes.size == 2500000


def test_other_files_are_the_ones_no_record_set_reads(card):
    # bundle.zip is read through readme.txt, the file of the "readme" record set.
    assert [(f.file.text, f.format, f.description) for f in card.other_files] == [
        ("article.pdf", "PDF", "The data article")
    ]


def test_most_frequent_values_come_from_the_statistics_of_the_metadata(card):
    # Values with spaces ("New York") are kept.
    assert field(card, "participants", "site").top_values == [
        ("Lausanne", 2),
        ("New York", 1),
        ("Geneva", 1),
    ]
    # No statistics in the metadata: none shown.
    assert field(card, "participants", "age").top_values == []


def test_most_frequent_value_without_top_10_freq():
    from fair2.card import _top_values

    assert _top_values({"top": "N", "freq": 15}) == [("N", 15)]
    assert _top_values(None) == []


def test_fields(card):
    age = field(card, "participants", "age")
    assert age.data_type == "Integer"
    assert age.unit == "Year (a)"
    assert age.description == "Age at inclusion"
    # Placeholder units aren't shown.
    assert field(card, "scores", "score").unit is None
    assert field(card, "participants", "site").unit is None


def test_statistics_are_the_ones_of_the_metadata(card):
    assert field(card, "participants", "age").stats == ColumnStats(1, minimum=28, maximum=45)
    assert field(card, "participants", "site").stats == ColumnStats(1, distinct=2)
    assert record_set(card, "participants").rows == 4
    # No statistics in the metadata: none, and no row count. The data isn't read.
    assert field(card, "participants", "visit").stats is None
    assert field(card, "scores", "score").stats is None
    assert record_set(card, "scores").rows is None


def test_the_data_is_not_read(db):
    # A closed connection: any query would fail.
    db.con.close()
    card = fair2.card(db)
    assert record_set(card, "participants").table == "participants"
    assert field(card, "participants", "age").stats.maximum == 45


def test_from_an_mlcroissant_dataset(db):
    card = fair2.card(db.dataset)
    assert card.name == "Test <dataset>"
    assert record_set(card, "participants").table is None
    assert record_set(card, "notes").skipped is None


def test_the_metadata_is_not_read_again(db, monkeypatch):
    import mlcroissant as mlc

    def fail(*args, **kwargs):
        raise AssertionError("the Croissant file was read again")

    monkeypatch.setattr(mlc, "Dataset", fail)
    monkeypatch.setattr(mlc.Metadata, "from_file", fail)
    assert fair2.card(db).name == "Test <dataset>"
