"""A small local FAIR² dataset for the tests: a CSV file, a Parquet file, an unsupported file."""

import hashlib
import json

import duckdb
import pytest

import croissant_duckdb

CONTEXT = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "sc": "https://schema.org/",
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "dct": "http://purl.org/dc/terms/",
    "fair2": "https://fair2.ai/ns/",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileObject": "cr:fileObject",
    "recordSet": "cr:recordSet",
    "source": "cr:source",
    "dataUseCases": "rai:dataUseCases",
    "dataLimitations": "rai:dataLimitations",
    "dataBiases": "rai:dataBiases",
    "dataCollection": "rai:dataCollection",
    "dataArticle": "fair2:dataArticle",
    "potentialBiases": "fair2:potentialBiases",
}


def file_object(folder, name, encoding_format):
    path = folder / name
    return {
        "@type": "cr:FileObject",
        "@id": f"files/{name}",
        "name": name,
        "contentUrl": name,
        "contentSize": str(path.stat().st_size),
        "encodingFormat": encoding_format,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def field(record_set, name, data_type, description, unit=None, column=None, statistics=None):
    node = {
        "@type": "cr:Field",
        "@id": f"{record_set}/{name}",
        "name": name,
        "description": description,
        "dataType": f"sc:{data_type}",
        "source": {
            "fileObject": {"@id": f"files/{record_set}"},
            "extract": {"column": column or name},
        },
    }
    if unit:
        node["unit"] = unit
    if statistics:
        node["statistics"] = statistics
    return node


@pytest.fixture
def dataset_path(tmp_path):
    """Writes the files and the FAIR² metadata, returns the path of the metadata."""
    # Leading zeros in the identifiers, a missing age, a missing site.
    (tmp_path / "participants.csv").write_text(
        "participant_id,age,site,visit\n"
        "007,36,Lausanne,2024-03-01\n"
        "042,,Geneva,2024-03-02\n"
        "100,28,,2024-03-05\n"
        "101,45,Lausanne,2024-03-09\n"
    )
    # Two row groups, a missing score in the second one.
    duckdb.sql(f"""
        COPY (
            SELECT * FROM (VALUES (1, 0.5), (2, 1.5), (3, NULL), (4, 9.25)) t(id, score)
        )
        TO '{tmp_path / "scores.parquet"}' (FORMAT parquet, ROW_GROUP_SIZE 2)
    """)
    (tmp_path / "notes.xlsx").write_bytes(b"not really an excel file")
    # Files that no record set reads, and an archive one record set reads a file of.
    (tmp_path / "article.pdf").write_bytes(b"%PDF-1.7")
    (tmp_path / "bundle.zip").write_bytes(b"PK")
    (tmp_path / "readme.txt").write_text("Read me\n")

    files = [
        file_object(tmp_path, "participants.csv", "text/csv"),
        file_object(tmp_path, "scores.parquet", "application/x-parquet"),
        file_object(tmp_path, "notes.xlsx", "application/vnd.ms-excel"),
    ]
    # A size in the megabytes, for the rendering.
    files[2]["contentSize"] = "2500000"
    article = file_object(tmp_path, "article.pdf", "application/pdf")
    article["description"] = "The data article"
    readme = file_object(tmp_path, "readme.txt", "text/plain")
    readme["containedIn"] = {"@id": "files/bundle.zip"}
    files += [article, file_object(tmp_path, "bundle.zip", "application/zip"), readme]
    record_sets = [
        {
            "@type": "cr:RecordSet",
            "@id": "participants.csv",
            "name": "participants",
            "description": "One row per participant.",
            "field": [
                field("participants.csv", "participant_id", "Text", "Participant identifier"),
                field(
                    "participants.csv",
                    "age",
                    "Integer",
                    "Age at inclusion",
                    unit={"label": "Year", "symbol": "a"},
                    # As FAIR² publishes statistics (pandas' describe()).
                    statistics={
                        "@type": "DescriptiveStatistics",
                        "count": 3,
                        "expected_number_of_values": 4,
                        "missing_values": 1,
                        "min": 28,
                        "max": 45,
                        "mean": 36.3,
                    },
                ),
                field(
                    "participants.csv",
                    "site",
                    "Text",
                    "Recruitment site",
                    unit={"label": "Unitless", "symbol": "一"},
                    # Statistics of the metadata, as FAIR² publishes them (pandas' value_counts()).
                    statistics={
                        "@type": "DescriptiveStatistics",
                        "count": 3,
                        "expected_number_of_values": 4,
                        "missing_values": 1,
                        "unique": 2,
                        "top": "Lausanne",
                        "freq": 2,
                        "top_10_freq": "site\nLausanne    2\nNew York    1\nGeneva      1\n"
                        "Name: count, dtype: int64",
                    },
                ),
                field("participants.csv", "visit", "Date", "Date of the first visit"),
            ],
        },
        {
            "@type": "cr:RecordSet",
            "@id": "scores.parquet",
            "name": "scores",
            "field": [
                field("scores.parquet", "score_id", "Integer", "Score identifier", column="id"),
                field(
                    "scores.parquet",
                    "score",
                    "Float",
                    "Test score <0-10>",
                    unit={"label": "Unknown", "symbol": "Unknown"},
                ),
            ],
        },
        {
            "@type": "cr:RecordSet",
            "@id": "notes.xlsx",
            "name": "notes",
            "field": [field("notes.xlsx", "note", "Text", "Free-text note")],
        },
        {
            "@type": "cr:RecordSet",
            "@id": "readme.txt",
            "name": "readme",
            "field": [field("readme.txt", "line", "Text", "A line of the readme")],
        },
    ]
    metadata = {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "name": "Test <dataset>",
        "description": "A small dataset for the tests.\n\nSecond paragraph.",
        "conformsTo": "http://mlcommons.org/croissant/1.0",
        "url": "https://sen.science/doi/10.71728/senscience.test-0001",
        "version": "1.2.0",
        "datePublished": "2026-05-19",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "citeAs": "Lovelace, A. 2026. Test dataset. Frontiers.",
        "keywords": ["memory; attention", "attention", "students"],
        "author": [
            {"@type": "Person", "name": "Ada", "familyName": "Lovelace"},
            {"@type": "Person", "name": "Grace Hopper", "familyName": "Hopper"},
        ],
        "spatialCoverage": {"@type": "Place", "description": "Lausanne, Switzerland"},
        "temporalCoverage": "2024-03/2024-04",
        "dataArticle": {
            "@id": "https://doi.org/10.3389/test.2026.1",
            "@type": "ScholarlyArticle",
            "name": "The test article",
        },
        "dataUseCases": ["Teaching", "Benchmarks"],
        "dataLimitations": ["Small sample"],
        "dataBiases": ["Students only"],
        "potentialBiases": "Recruited in two cities.",
        "dataCollection": "Questionnaires during the first visit.",
        "distribution": files,
        "recordSet": record_sets,
    }
    path = tmp_path / "fair2.json"
    path.write_text(json.dumps(metadata))
    return path


@pytest.fixture
def db(dataset_path):
    return croissant_duckdb.connect(str(dataset_path), verbose=False)
