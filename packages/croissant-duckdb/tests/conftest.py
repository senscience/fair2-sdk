"""A small local Croissant dataset (CSV and Parquet files) for the tests."""

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
    "dct": "http://purl.org/dc/terms/",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileObject": "cr:fileObject",
    "fileProperty": "cr:fileProperty",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "md5": "cr:md5",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
}


def file_object(folder, name, encoding_format):
    path = folder / name
    return {
        "@type": "cr:FileObject",
        # Distinct from the record set @ids: in JSON-LD, nodes with the same @id are the same node.
        "@id": f"files/{name}",
        "name": name,
        "contentUrl": name,
        "encodingFormat": encoding_format,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "0" * 64,
    }


NO_NAME = object()


def record_set(record_set_id, file_id, fields, name=None):
    """fields: (field name, column, data type) tuples; a field name None gives a field without name.

    Field @ids are <record set @id>/<column>: mlcroissant rejects @ids with spaces, and names may
    have some.

    name: the record set's name (its @id by default), or NO_NAME for a record set without name.
    """
    node = {"@type": "cr:RecordSet", "@id": record_set_id}
    if name is not NO_NAME:
        node["name"] = record_set_id if name is None else name
    node["field"] = []
    for field, column, data_type in fields:
        field_node = {
            "@type": "cr:Field",
            "@id": f"{record_set_id}/{column.strip()}",
            "dataType": data_type if ":" in data_type else f"sc:{data_type}",
            "source": {"fileObject": {"@id": f"files/{file_id}"}, "extract": {"column": column}},
        }
        if field is not None:
            field_node["name"] = field
        node["field"].append(field_node)
    return node


@pytest.fixture
def dataset_path(tmp_path):
    """Writes the files and the Croissant metadata, returns the path of the metadata."""
    con = duckdb.connect()
    # A CSV with an identifier that has leading zeros, and a header with a trailing space.
    (tmp_path / "people.csv").write_text(
        "person_id,name ,age\n007,Ada,36\n042,Grace,45\n100,Linus,28\n"
    )
    con.sql(f"""
        COPY (
            SELECT * FROM (VALUES (1, 'a', 1.5), (2, 'b', 2.5), (3, 'c', NULL)) t(id, label, score)
        )
        TO '{tmp_path / "scores.parquet"}' (FORMAT parquet)
    """)
    # One column per declared type; "2" in a Float column and "7" in an Int32 column.
    (tmp_path / "measures.csv").write_text(
        "code,score,ok,day,at,small\n"
        "001,1.5,true,2024-03-01,2024-03-01 10:30:00,7\n"
        "002,2,false,2024-03-02,2024-03-02 11:00:00,8\n"
    )
    # "NA" in a column declared Integer.
    (tmp_path / "mismatch.csv").write_text("id,count\n1,3\n2,NA\n")
    (tmp_path / "sheet.xlsx").write_bytes(b"not really an excel file")
    (tmp_path / "dup").mkdir()
    con.sql(f"COPY (SELECT 1 AS x) TO '{tmp_path / 'dup' / 'items.parquet'}' (FORMAT parquet)")
    con.sql(f"COPY (SELECT 2 AS x) TO '{tmp_path / 'items.parquet'}' (FORMAT parquet)")

    files = [
        file_object(tmp_path, "people.csv", "text/csv"),
        file_object(tmp_path, "scores.parquet", "application/x-parquet"),
        file_object(tmp_path, "measures.csv", "text/csv"),
        file_object(tmp_path, "mismatch.csv", "text/csv"),
        file_object(
            tmp_path,
            "sheet.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        file_object(tmp_path, "missing.parquet", "application/x-parquet"),
        file_object(tmp_path, "items.parquet", "application/x-parquet"),
        file_object(tmp_path, "dup/items.parquet", "application/x-parquet"),
    ]
    record_sets = [
        record_set(
            "people",
            "people.csv",
            [
                ("person_id", "person_id", "Text"),
                ("name", "name ", "Text"),
                ("age", "age", "Integer"),
            ],
        ),
        # Field names different from the column names.
        record_set(
            "scores",
            "scores.parquet",
            [
                ("score_id", "id", "Integer"),
                ("label", "label", "Text"),
                ("score", "score", "Float"),
            ],
        ),
        record_set(
            "measures",
            "measures.csv",
            [
                ("code", "code", "Text"),
                ("score", "score", "Float"),
                ("ok", "ok", "Boolean"),
                ("day", "day", "Date"),
                ("at", "at", "DateTime"),
                ("small", "small", "cr:Int32"),
            ],
        ),
        record_set(
            "mismatch", "mismatch.csv", [("id", "id", "Integer"), ("count", "count", "Integer")]
        ),
        record_set("sheet", "sheet.xlsx", [("cell", "A", "Text")]),
        record_set("missing", "missing.parquet", [("x", "x", "Integer")]),
        record_set("bad_column", "scores.parquet", [("nope", "does_not_exist", "Text")]),
        # Columns missing from a CSV file: a text one (passed to DuckDB as a type) and a number.
        record_set("bad_csv_text", "people.csv", [("nope", "no_text", "Text")]),
        record_set("bad_csv_number", "people.csv", [("nope", "no_number", "Integer")]),
        # Names are used as they are: paths, spaces, parentheses.
        record_set("data/items.parquet", "items.parquet", [("x", "x", "Integer")]),
        record_set("dup/items.parquet", "dup/items.parquet", [("x", "x", "Integer")]),
        record_set(
            "labelled",
            "scores.parquet",
            [("Score (0-1)", "score", "Float")],
            name="Scores (labelled)",
        ),
        # No name: the @id is used, for the record set and for its field.
        record_set("unnamed", "scores.parquet", [(None, "id", "Integer")], name=NO_NAME),
        # Same name as "scores" for DuckDB, which compares names case-insensitively.
        record_set("scores_again", "scores.parquet", [("id", "id", "Integer")], name="SCORES"),
        # Two fields with the same name for DuckDB.
        record_set(
            "twice", "scores.parquet", [("label", "label", "Text"), ("LABEL", "id", "Integer")]
        ),
    ]
    metadata = {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "name": "test_dataset",
        "description": "A small dataset for the tests.",
        "conformsTo": "http://mlcommons.org/croissant/1.0",
        "url": "https://example.org/dataset",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "distribution": files,
        "recordSet": record_sets,
    }
    path = tmp_path / "fair2.json"
    path.write_text(json.dumps(metadata))
    return path


@pytest.fixture
def db(dataset_path):
    """The DuckDB database of the test dataset."""
    return croissant_duckdb.connect(str(dataset_path), verbose=False)
