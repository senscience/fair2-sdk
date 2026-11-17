import pytest

import fair2_notebook
from fair2_notebook.card import ColumnStats


@pytest.fixture
def card(dataset):
    return fair2_notebook.card(dataset)


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
    assert [a.text for a in card.authors] == ["Ada Lovelace", "Grace Hopper"]
    # Linked to their ORCID when the metadata gives one
    assert [a.url for a in card.authors] == ["https://orcid.org/0000-0002-1825-0097", None]
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
    assert participants.file.text == "participants.csv"
    assert participants.format == "CSV"
    assert participants.rows == 4
    assert record_set(card, "scores").format == "Parquet"
    assert record_set(card, "notes").size == 2500000


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
    from fair2_notebook.card import _top_values

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


def test_the_data_is_not_read(dataset, dataset_path):
    # The files aren't real CSV and Parquet files: reading them would fail.
    (dataset_path.parent / "participants.csv").write_text('not, a, valid\n"csv')
    card = fair2_notebook.card(dataset)
    assert field(card, "participants", "age").stats.maximum == 45


def test_the_metadata_is_not_read_again(dataset, monkeypatch):
    import mlcroissant as mlc

    def fail(*args, **kwargs):
        raise AssertionError("the Croissant file was read again")

    monkeypatch.setattr(mlc, "Dataset", fail)
    monkeypatch.setattr(mlc.Metadata, "from_file", fail)
    assert fair2_notebook.card(dataset).name == "Test <dataset>"


def test_data_portal_and_archive(card):
    assert card.data_portal.url == "https://sen.science/doi/10.71728/senscience.test-0001"
    assert card.data_archive.url == "https://doi.org/10.5281/zenodo.0000001"


def test_links_given_as_a_node_uri():
    # How mlcroissant gives some @id nodes back (e.g. dataPortal in published FAIR² metadata)
    from fair2_notebook.card import _link

    link = _link({"uri": "https://sen.science/doi/10.71728/x"})
    assert (link.text, link.url) == ("https://sen.science/doi/10.71728/x",) * 2


@pytest.mark.parametrize(
    "author",
    [
        # As the published files give it, read by mlcroissant (t3x9-1z2t)
        {"identifier": {"uri": "https://orcid.org/0000-0002-1825-0097", "propertyID": "ORCID"}},
        # As the FAIR² specification's example gives it
        {"identifier": "https://orcid.org/0000-0002-1825-0097"},
        {"sameAs": ["https://example.org/x", "http://orcid.org/0000-0002-1825-0097"]},
        # An iD alone, said to be an ORCID
        {"identifier": {"value": "0000-0002-1825-0097", "propertyID": "ORCID"}},
    ],
)
def test_orcid_of_an_author(author):
    from fair2_notebook.card import _orcid

    assert _orcid(author) == "https://orcid.org/0000-0002-1825-0097"


@pytest.mark.parametrize(
    "author",
    [
        {},
        {"identifier": "https://sen.science/authors/c1b96691"},
        # An iD-like number that isn't said to be an ORCID
        {"identifier": "0000-0002-1825-0097"},
        {"identifier": {"value": "0000-0002-1825-0097", "propertyID": "ISNI"}},
    ],
)
def test_no_orcid(author):
    from fair2_notebook.card import _orcid

    assert _orcid(author) is None
