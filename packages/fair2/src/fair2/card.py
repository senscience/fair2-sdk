"""Dataset cards: what a FAIR² dataset is, how to cite and use it, and what its record sets contain.

Everything comes from the metadata already read by mlcroissant: the card reads neither the Croissant
file again nor the data. Statistics are the ones the metadata declares for its fields. With a
`croissant_duckdb.Database`, the card also says which DuckDB table has each record set.
"""

from __future__ import annotations

import dataclasses
import re
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

import mlcroissant as mlc

from croissant_duckdb import Database
from croissant_duckdb.naming import name_of
from fair2.themes import FRONTIERS, Theme

# Sections of the "Responsible use" part: label, and the metadata properties shown under it, in
# order. Croissant RAI properties, and the FAIR² ones used by some datasets instead.
RESPONSIBLE_USE = [
    ("Intended uses", ["dataUseCases"]),
    ("Limitations", ["dataLimitations", "licenseConstraints", "distributionRestrictions"]),
    ("Biases", ["dataBiases", "potentialBiases"]),
    ("Personal and sensitive information", ["personalSensitiveInformation"]),
    ("Ethical considerations", ["ethicalConsiderations"]),
    ("Social impact", ["dataSocialImpact"]),
    ("Data collection", ["dataCollection", "dataCollectionType", "dataCollectionTimeframe"]),
    ("Raw data", ["dataCollectionRawData"]),
    ("Missing data", ["dataCollectionMissingData"]),
    (
        "Processing",
        [
            "dataPreprocessingProtocol",
            "dataManipulationProtocol",
            "dataImputationProtocol",
            "dataAnnotationProtocol",
        ],
    ),
    ("Maintenance", ["dataReleaseMaintenancePlan"]),
]

LICENSES = {
    "https://opendatacommons.org/licenses/by/1-0/": "ODC-BY 1.0",
    "https://opendatacommons.org/licenses/odbl/1-0/": "ODbL 1.0",
    "https://opendatacommons.org/licenses/pddl/1-0/": "PDDL 1.0",
    "https://creativecommons.org/licenses/by/4.0/": "CC BY 4.0",
    "https://creativecommons.org/licenses/by-sa/4.0/": "CC BY-SA 4.0",
    "https://creativecommons.org/licenses/by-nc/4.0/": "CC BY-NC 4.0",
    "https://creativecommons.org/publicdomain/zero/1.0/": "CC0 1.0",
}

NO_UNITS = ("unknown", "unitless")

FORMATS = {
    "text/csv": "CSV",
    "text/tab-separated-values": "TSV",
    "application/x-parquet": "Parquet",
    "application/vnd.apache.parquet": "Parquet",
    "application/json": "JSON",
    "application/x-sqlite3": "SQLite",
    "application/zip": "ZIP",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
    "text/plain": "Text",
    "application/pdf": "PDF",
}


@dataclasses.dataclass(frozen=True)
class Link:
    text: str
    url: str | None = None


@dataclasses.dataclass(frozen=True)
class ColumnStats:
    """The statistics of a field, as its metadata declares them (`statistics`)."""

    missing: int | None
    minimum: object = None
    maximum: object = None
    distinct: int | None = None


@dataclasses.dataclass(frozen=True)
class Field:
    name: str
    data_type: str | None
    unit: str | None
    description: str | None
    stats: ColumnStats | None = None
    """From the field's statistics in the metadata, when it has some."""
    top_values: list[tuple[str, int]] = dataclasses.field(default_factory=list)
    """The most frequent values and their counts, from the field's statistics in the metadata."""


@dataclasses.dataclass(frozen=True)
class RecordSet:
    id: str
    name: str
    description: str | None
    file: Link | None
    format: str | None
    size: int | str | None
    """Size of the file: bytes, or the contentSize as written when it isn't a number of bytes."""
    fields: list[Field]
    table: str | None = None
    """DuckDB table or view, with a `croissant_duckdb.Database`."""
    skipped: str | None = None
    """Why the record set has no table, with a `croissant_duckdb.Database`."""
    rows: int | None = None
    """From the statistics of its fields in the metadata, when they have some."""


@dataclasses.dataclass(frozen=True)
class File:
    """A file or file set of the distribution that no record set reads."""

    file: Link
    format: str | None
    size: int | str | None
    description: str | None


# The card's text representation is short: Jupyter stores it next to the HTML in the notebook.
@dataclasses.dataclass(frozen=True, repr=False)
class DatasetCard:
    name: str
    description: str | None
    doi: str | None
    url: str | None
    version: str | None
    date_published: str | None
    license: Link | None
    authors: list[str]
    cite_as: str | None
    data_article: Link | None
    source: Link | None
    """The Croissant file the metadata was read from."""
    keywords: list[str]
    spatial_coverage: list[str]
    temporal_coverage: list[str]
    funders: list[str]
    responsible_use: list[tuple[str, list[str]]]
    """(label, texts) of the sections that have content, in the order of `RESPONSIBLE_USE`."""
    record_sets: list[RecordSet]
    other_files: list[File] = dataclasses.field(default_factory=list)
    """Files and file sets that no record set reads: SQLite databases, PDFs, images..."""
    theme: Theme | None = dataclasses.field(default=None, compare=False)
    """How the card looks: logo, colours, typeface. None for plain HTML."""
    id: str = dataclasses.field(
        default_factory=lambda: f"fair2-card-{uuid.uuid4().hex[:12]}", compare=False
    )
    """The id of its HTML element: unique, for its search script to find it in the notebook."""

    def html(self) -> str:
        """The card as an HTML fragment."""
        from fair2.html import render

        return render(self, self.theme)

    def _repr_html_(self) -> str:
        # Displayed by Jupyter when the card is the last expression of a cell.
        return self.html()

    def __repr__(self) -> str:
        return f"<DatasetCard {self.name!r}: {len(self.record_sets)} record sets>"


def card(source: Database | mlc.Dataset, *, theme: Theme | None = FRONTIERS) -> DatasetCard:
    """The card of a dataset, from its metadata only: no data is read.

    Args:
        source: A `croissant_duckdb.Database`, which also gives the DuckDB table of each record
            set, or an `mlcroissant.Dataset`.
        theme: The logo, colours and typeface of the card (`fair2.themes`), the Frontiers one by
            default. None for plain HTML, which follows the notebook's look.
    """
    db = source if isinstance(source, Database) else None
    dataset = db.dataset if db is not None else source
    metadata = dataset.metadata
    # Every property of the metadata, including the ones mlcroissant has no attribute for.
    properties = metadata.to_json()

    doi = _doi(properties)
    return DatasetCard(
        name=metadata.name,
        description=metadata.description,
        doi=doi,
        url=_first(_texts(properties.get("url"))),
        version=_first(_texts(properties.get("version"))),
        date_published=_first(_texts(properties.get("datePublished"))),
        license=_license(properties.get("license")),
        authors=_authors(properties.get("author") or properties.get("creator")),
        cite_as=_first(_texts(properties.get("citeAs"))),
        data_article=_link(properties.get("dataArticle")),
        # The URL or path mlcroissant read: a Dataset made from a dict has none.
        source=_link(dataset.jsonld) if isinstance(dataset.jsonld, str) else None,
        keywords=_keywords(properties.get("keywords")),
        spatial_coverage=_texts(properties.get("spatialCoverage")),
        temporal_coverage=_texts(properties.get("temporalCoverage")),
        funders=_funders(properties.get("funding")),
        responsible_use=[
            (label, texts)
            for label, keys in RESPONSIBLE_USE
            if (texts := [text for key in keys for text in _texts(properties.get(key))])
        ],
        record_sets=[_record_set(record_set, metadata, db) for record_set in metadata.record_sets],
        other_files=_other_files(metadata),
        theme=theme,
    )


def _record_set(record_set, metadata, db: Database | None) -> RecordSet:
    file_objects = {node.id: node for node in metadata.distribution}
    sources = [field.source.file_object for field in record_set.fields if field.source]
    file_object = file_objects.get(next((s for s in sources if s), None))
    statistics = [(field.extra_properties or {}).get("statistics") for field in record_set.fields]
    return RecordSet(
        id=record_set.id,
        name=name_of(record_set),
        description=record_set.description,
        file=_file(file_object),
        format=_format(file_object),
        size=_size(getattr(file_object, "content_size", None)),
        fields=[
            Field(
                name=name_of(field),
                data_type=", ".join(_local_name(t) for t in field.data_types) or None,
                unit=_unit((field.extra_properties or {}).get("unit")),
                description=field.description,
                stats=_stats(field_statistics),
                top_values=_top_values(field_statistics),
            )
            for field, field_statistics in zip(record_set.fields, statistics, strict=True)
        ],
        table=db.tables.get(record_set.id) if db is not None else None,
        skipped=db.skipped.get(record_set.id) if db is not None else None,
        rows=max(filter(None, map(_rows, statistics)), default=None),
    )


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _stats(statistics: Any) -> ColumnStats | None:
    """A field's DescriptiveStatistics in the metadata: missing values, min and max, distinct."""
    if not isinstance(statistics, dict):
        return None
    missing = _number(statistics.get("missing_values"))
    distinct = _number(statistics.get("unique"))
    return ColumnStats(
        missing=int(missing) if missing is not None else None,
        minimum=_number(statistics.get("min")),
        maximum=_number(statistics.get("max")),
        distinct=int(distinct) if distinct is not None else None,
    )


def _rows(statistics: Any) -> int | None:
    """The number of rows of a field's record set, from its statistics in the metadata."""
    if not isinstance(statistics, dict):
        return None
    expected = _number(statistics.get("expected_number_of_values"))
    if expected is not None:
        return int(expected)
    count, missing = _number(statistics.get("count")), _number(statistics.get("missing_values"))
    return int(count + (missing or 0)) if count is not None else None


def _other_files(metadata) -> list[File]:
    """The files and file sets that no field reads, directly or from an archive."""
    nodes = {node.id: node for node in metadata.distribution}
    used = set()
    fields = [field for record_set in metadata.record_sets for field in record_set.fields]
    while fields:
        field = fields.pop()
        fields.extend(field.sub_fields or [])
        if field.source:
            used.update(i for i in (field.source.file_object, field.source.file_set) if i)
    # The archives that contain a file in use are in use too.
    pending = list(used)
    while pending:
        node = nodes.get(pending.pop())
        for container in getattr(node, "contained_in", None) or []:
            container_id = container if isinstance(container, str) else _source_id(container)
            if container_id and container_id not in used:
                used.add(container_id)
                pending.append(container_id)
    return [
        File(
            file=_file(node) or Link(node.id),
            format=_format(node),
            size=_size(getattr(node, "content_size", None)),
            description=node.description,
        )
        for node in metadata.distribution
        if node.id not in used
    ]


def _source_id(source) -> str | None:
    return getattr(source, "file_object", None) or getattr(source, "file_set", None)


def _texts(value: Any) -> list[str]:
    """The texts of a property: a string, a list of strings, or nodes with a name or description."""
    if value is None:
        return []
    if isinstance(value, list):
        return [text for item in value for text in _texts(item)]
    if isinstance(value, dict):
        text = value.get("description") or value.get("name") or value.get("@value")
        return _texts(text)
    text = str(value).strip()
    return [text] if text else []


def _first(texts: list[str]) -> str | None:
    return texts[0] if texts else None


def _doi(properties: dict) -> str | None:
    """The DOI of the dataset: its identifier, or the DOI in its URL (sen.science/doi/<DOI>)."""
    for text in _texts(properties.get("identifier")) + _texts(properties.get("url")):
        if match := re.search(r"(?:^|doi\.org/|/doi/)(10\.\d{4,}/[^\s/?#]+)", text):
            return match.group(1)
    return None


def _license(value: Any) -> Link | None:
    url = _first(_texts(value))
    if url is None:
        return None
    name = LICENSES.get(url.rstrip("/") + "/") or LICENSES.get(url)
    return Link(name or url, url if _is_url(url) else None)


def _authors(value: Any) -> list[str]:
    """Author names. FAIR² metadata gives the given name in `name`, the family name apart."""
    authors = []
    for author in value if isinstance(value, list) else [value] if value else []:
        if not isinstance(author, dict):
            authors.extend(_texts(author))
            continue
        name = (author.get("name") or "").strip()
        family = (author.get("familyName") or "").strip()
        if family and family not in name:
            name = f"{name} {family}".strip()
        if name:
            authors.append(name)
    return authors


def _link(value: Any) -> Link | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        url = value.get("url") or value.get("@id")
        text = value.get("name") or url
        return Link(text, url if _is_url(url) else None) if text else None
    text = _first(_texts(value))
    return Link(text, text if _is_url(text) else None) if text else None


def _keywords(value: Any) -> list[str]:
    """Keywords, also when several are given in one string separated by semicolons."""
    keywords = []
    for text in _texts(value):
        for keyword in text.split(";"):
            if (keyword := keyword.strip()) and keyword not in keywords:
                keywords.append(keyword)
    return keywords


def _funders(value: Any) -> list[str]:
    """Names of the funders of the grants, or of the grants when they have no funder."""
    funders = []
    for grant in value if isinstance(value, list) else [value] if value else []:
        names = _texts(grant.get("funder")) if isinstance(grant, dict) else []
        for name in names or _texts(grant):
            if name not in funders:
                funders.append(name)
    return funders


def _file(file_object) -> Link | None:
    if file_object is None:
        return None
    url = getattr(file_object, "content_url", None)
    if url:
        # The file name, from the URL: the name of FileObjects is sometimes form-encoded.
        return Link(unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]), url)
    return Link(unquote(file_object.name)) if file_object.name else None


def _format(file_object) -> str | None:
    formats = getattr(file_object, "encoding_formats", None) or []
    return ", ".join(FORMATS.get(f, f) for f in formats) or None


def _size(content_size: Any) -> int | str | None:
    if content_size is None:
        return None
    text = str(content_size).strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    # "1234 B", as mlcroissant writes sizes in bytes.
    if match := re.fullmatch(r"(\d+)\s*B", text):
        return int(match.group(1))
    return text or None


def _top_values(statistics: Any) -> list[tuple[str, int]]:
    """The most frequent values of a field, from its DescriptiveStatistics in the metadata.

    `top_10_freq` is the text pandas prints for `value_counts()`: the column name, a "value  count"
    line per value, and a "Name: count, dtype: int64" line. Without it, `top` and `freq` give the
    most frequent value.
    """
    if not isinstance(statistics, dict):
        return []
    values = []
    lines = str(statistics.get("top_10_freq") or "").splitlines()
    # The first line is the column name.
    for line in lines[1:]:
        if line.startswith("Name:"):
            break
        value, _, count = line.rstrip().rpartition(" ")
        if value.strip() and count.isdigit():
            values.append((value.strip(), int(count)))
    if not values and statistics.get("top") is not None and str(statistics.get("freq")).isdigit():
        values.append((str(statistics["top"]), int(statistics["freq"])))
    return values


def _unit(value: Any) -> str | None:
    """The unit of a field: its label, with its symbol when it adds something ("Second (s)").

    Placeholder units (QUDT's "Unknown" and "Unitless", given to text fields) aren't shown.
    """
    if isinstance(value, dict):
        label = (value.get("label") or "").strip()
        symbol = (value.get("symbol") or "").strip()
        if label.lower() in NO_UNITS:
            return None
        if symbol.lower() in ("", label.lower()) or symbol.lower() in NO_UNITS:
            symbol = ""
        if label and symbol:
            return f"{label} ({symbol})"
        return label or symbol or None
    return _first(_texts(value))


def _local_name(data_type) -> str:
    """The name of a data type: "Integer" for https://schema.org/Integer, "Int32" for cr:Int32."""
    return re.split(r"[/:#]", str(data_type))[-1]


def _is_url(text: str | None) -> bool:
    return bool(text) and text.startswith(("https://", "http://"))
