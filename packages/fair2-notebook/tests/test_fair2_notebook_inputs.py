import json

import mlcroissant as mlc
import pandas as pd
import pytest

from fair2_notebook import Inputs


@pytest.fixture
def inputs(dataset_path):
    # A real Parquet file (the card's tests only need the files to exist)
    pd.DataFrame({"id": [1, 2], "score": [0.5, 1.5]}).to_parquet(
        dataset_path.parent / "scores.parquet"
    )
    return Inputs(mlc.Dataset(str(dataset_path)))


def test_reads_a_csv_file_by_its_name(inputs):
    table = inputs.read("participants.csv")
    assert list(table.columns) == ["participant_id", "age", "site", "visit"]
    assert len(table) == 4
    # Read as the figures' code read it: pandas' CSV reader, its types
    assert table["participant_id"].tolist() == [7, 42, 100, 101]


def test_reads_a_parquet_file_with_pyarrow(inputs):
    assert inputs.read("scores.parquet")["score"].tolist() == [0.5, 1.5]


def test_reads_with_options(inputs):
    table = inputs.read("participants.csv", dtype={"participant_id": str})
    assert table["participant_id"].tolist() == ["007", "042", "100", "101"]
    # Other options, another table: the first one is unchanged
    assert inputs.read("participants.csv")["participant_id"].tolist() == [7, 42, 100, 101]


def test_each_file_is_read_once_and_copies_are_returned(inputs, monkeypatch):
    calls = []
    read_csv = pd.read_csv
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: calls.append(1) or read_csv(*a, **k))
    first = inputs.read("participants.csv")
    first["age"] = 0  # the code changes its copy
    second = inputs.read("participants.csv")
    assert len(calls) == 1
    assert second["age"].tolist()[0] == 36


def test_prepared_tables_as_returned(inputs):
    table = pd.DataFrame({"x": pd.Categorical(["a", "b"])})
    inputs.prepare("10a70c02-6f8b-4ed0-8570-48e8a69bc9c6", table)
    read = inputs.read("10a70c02-6f8b-4ed0-8570-48e8a69bc9c6")
    # As returned: its types kept, and a copy
    assert read["x"].dtype == "category"
    assert read is not table
    # Also with ".csv" after its id, as the figures' code could read it
    assert inputs.read("10a70c02-6f8b-4ed0-8570-48e8a69bc9c6.csv").equals(read)


def test_names_as_the_code_reads_them(dataset_path):
    # Published form-encoded, read decoded; a file without an extension, read with ".csv"
    metadata = json.loads(dataset_path.read_text())
    participants = next(f for f in metadata["distribution"] if f["name"] == "participants.csv")
    participants["name"] = "data%2Fcsv%2Fparticipants"
    path = dataset_path.parent / "encoded.json"
    path.write_text(json.dumps(metadata))
    inputs = Inputs(mlc.Dataset(str(path)))
    assert len(inputs.read("data/csv/participants")) == 4
    assert len(inputs.read("data/csv/participants.csv")) == 4
    assert len(inputs.read("data%2Fcsv%2Fparticipants")) == 4


def published(dataset_path, name, changes):
    """The test dataset with some files moved: {file name: (published name, location)}."""
    metadata = json.loads(dataset_path.read_text())
    for file in metadata["distribution"]:
        if file["name"] in changes:
            new_name, location = changes[file["name"]]
            target = dataset_path.parent / location
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((dataset_path.parent / file["contentUrl"]).read_bytes())
            file["name"], file["contentUrl"] = new_name, location
    path = dataset_path.parent / name
    path.write_text(json.dumps(metadata))
    return Inputs(mlc.Dataset(str(path)))


def test_names_with_their_folder_in_the_upload(dataset_path):
    # Published as "participants.csv"; the code names it by its path in the upload, which only
    # the location keeps
    moved = {"participants.csv": ("participants.csv", "t/participants.csv")}
    inputs = published(dataset_path, "folders.json", moved)
    for name in ("t/participants.csv", "t%2Fparticipants.csv", "t/participants"):
        assert len(inputs.read(name)) == 4


def test_csv_added_or_removed(dataset_path):
    # Published with ".csv" and read without (the derived tables), and the other way round
    inputs = published(
        dataset_path,
        "csv.json",
        {"participants.csv": ("PARTICIPANTS", "sheets/PARTICIPANTS")},
    )
    assert len(inputs.read("sheets/PARTICIPANTS.csv")) == 4
    derived = published(
        dataset_path,
        "derived.json",
        {"participants.csv": ("0d4f.csv", "0d4f.csv")},
    )
    assert len(derived.read("0d4f")) == 4


def test_names_with_a_plus_in_their_location(dataset_path):
    # A "+" kept as it is in the location: read as given, not decoded to a space
    inputs = published(dataset_path, "plus.json", {"participants.csv": ("Site+A", "Site+A")})
    assert len(inputs.read("Site+A")) == 4


def test_a_name_reading_several_files(dataset_path):
    inputs = published(
        dataset_path,
        "several.json",
        {"participants.csv": ("a.csv", "a/data.csv"), "notes.xlsx": ("b.csv", "b/data.csv")},
    )
    with pytest.raises(KeyError, match="'data.csv' reads several files of the dataset"):
        inputs.read("data.csv")
    assert len(inputs.read("a/data.csv")) == 4


def test_urls_with_other_characters_than_ascii(dataset_path, tmp_path, monkeypatch):
    metadata = json.loads(dataset_path.read_text())
    participants = next(f for f in metadata["distribution"] if f["name"] == "participants.csv")
    participants["name"] = "características.csv"
    participants["contentUrl"] = "https://sen.science/doi/x/características%20(1).csv"
    path = tmp_path / "accents.json"
    path.write_text(json.dumps(metadata))
    downloads = []

    def urlretrieve(url, destination):
        downloads.append(url)
        destination.write_bytes((dataset_path.parent / "participants.csv").read_bytes())

    monkeypatch.setattr("urllib.request.urlretrieve", urlretrieve)
    inputs = Inputs(mlc.Dataset(str(path)), folder=tmp_path / "downloads")
    assert len(inputs.read("caracter%C3%ADsticas.csv")) == 4
    # Encoded for HTTP, what was already encoded kept
    assert downloads == ["https://sen.science/doi/x/caracter%C3%ADsticas%20(1).csv"]


def test_an_unknown_name(inputs):
    with pytest.raises(KeyError, match="'nothing.csv' is not a file of the dataset"):
        inputs.read("nothing.csv")


def test_files_published_at_urls_are_downloaded_once(dataset_path, tmp_path, monkeypatch):
    metadata = json.loads(dataset_path.read_text())
    for file in metadata["distribution"]:
        file["contentUrl"] = f"https://sen.science/doi/10.71728/x/{file['contentUrl']}"
    path = tmp_path / "remote.json"
    path.write_text(json.dumps(metadata))
    downloads = []

    def urlretrieve(url, destination):
        downloads.append(url)
        local = dataset_path.parent / url.rsplit("/", 1)[1]
        destination.write_bytes(local.read_bytes())

    monkeypatch.setattr("urllib.request.urlretrieve", urlretrieve)
    inputs = Inputs(mlc.Dataset(str(path)), folder=tmp_path / "downloads")
    inputs.read("participants.csv")
    inputs.read("participants.csv", usecols=["age"])
    assert downloads == ["https://sen.science/doi/10.71728/x/participants.csv"]
