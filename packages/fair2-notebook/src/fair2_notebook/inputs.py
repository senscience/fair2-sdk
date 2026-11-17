"""The inputs of a notebook's code: the files of the dataset, and the tables its cells prepare.

The figures of a FAIR² data article were made by code reading its inputs by name,
`sense_input(name)`: a file of the dataset, or a table prepared by an earlier step. `Inputs` gives
that function to the notebook, from the dataset as mlcroissant reads it:

    inputs = Inputs(dataset)
    sense_input = inputs.read
    ...
    inputs.prepare("<step id>", result)

The files are read with pandas, not with mlcroissant's records: Parquet with pyarrow, the others
as CSV, as the code that made the figures read them. Each file is downloaded once, and read once
per set of options; every read returns a copy, which the code can change.
"""

from __future__ import annotations

import os
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote, unquote_plus, urljoin, urlparse, urlsplit, urlunsplit

import mlcroissant as mlc
import pandas as pd

PARQUET = ("application/x-parquet", "application/vnd.apache.parquet")


class Inputs:
    """The files of a dataset and the tables prepared from them, by name."""

    def __init__(self, dataset: mlc.Dataset, *, folder: str | os.PathLike | None = None):
        """
        Args:
            dataset: The dataset, as mlcroissant reads it: its FileObjects are its files.
            folder: Where the files are downloaded: a temporary folder by default.
        """
        base = dataset.jsonld if isinstance(dataset.jsonld, str) else None
        # Name -> (location, format). The names as the code reads them: decoded (some are
        # published form-encoded: "data%2Fparquet%2F...").
        self._files: dict[str, tuple[str, str | None]] = {}
        for node in dataset.metadata.distribution:
            url = getattr(node, "content_url", None)
            if not url or not node.name:
                continue
            formats = getattr(node, "encoding_formats", None) or []
            self._files[unquote_plus(node.name)] = (
                _location(url, base),
                formats[0] if formats else None,
            )
        self._folder = Path(folder) if folder else None
        self._downloads: dict[str, Path] = {}
        self._tables: dict[tuple[str, str], pd.DataFrame] = {}
        self._prepared: dict[str, pd.DataFrame] = {}

    @property
    def names(self) -> list[str]:
        """The names of the files, then of the prepared tables."""
        return [*self._files, *self._prepared]

    def prepare(self, name: str, table: pd.DataFrame) -> None:
        """Keeps a table prepared by the code, as it is, for the code reading it by its name."""
        self._prepared[name] = table

    def read(self, name: str, **options) -> pd.DataFrame:
        """A copy of a prepared table or of a file's table, by its name.

        A prepared table can also be read with ".csv" after its name. A file is read by its name,
        or by its path in the upload as the code that made the figures named it (the end of its
        location), form-encoded or not, with or without ".csv". `options` are pandas'
        (`read_parquet`, `read_csv`): a file read with other options is read again.
        """
        if name in self._prepared:
            return self._prepared[name].copy()
        if name.endswith(".csv") and name[:-4] in self._prepared:
            return self._prepared[name[:-4]].copy()
        file = self._file(name)
        key = (file, repr(sorted(options.items())))
        if key not in self._tables:
            location, file_format = self._files[file]
            path = self._local(file, location)
            if file_format in PARQUET or file.lower().endswith(".parquet"):
                self._tables[key] = pd.read_parquet(path, engine="pyarrow", **options)
            else:
                self._tables[key] = pd.read_csv(path, **options)
        return self._tables[key].copy()

    def _file(self, name: str) -> str:
        """The file a name reads, as the platform that ran the code named its files.

        The code names a file by its path in the upload ("tables/scores.csv"), as given or
        form-encoded ("tables%2Fscores.csv"), with or without ".csv". The metadata keeps that path
        at the end of the file's location, not in its name ("scores.csv"): a name is the file's
        name, or the end of its location.
        """
        candidates = set()
        for form in (name, unquote_plus(name)):
            candidates |= {form, form + ".csv"}
            if form.endswith(".csv"):
                candidates.add(form[:-4])
        for candidate in (name, unquote_plus(name), *sorted(candidates)):
            if candidate in self._files:
                return candidate
        # By location: the same file can be listed twice, under the same location
        matches = {}
        for file, (location, _) in self._files.items():
            path = _path(location)
            if any(path.endswith("/" + candidate) for candidate in candidates):
                matches.setdefault(location, file)
        if len(matches) == 1:
            return next(iter(matches.values()))
        if matches:
            files = sorted(matches.values())
            raise KeyError(f"{name!r} reads several files of the dataset: {files}")
        raise KeyError(f"{name!r} is not a file of the dataset nor a prepared table: {self.names}")

    def _local(self, name: str, location: str) -> Path:
        """The file on this machine: downloaded once, or the local file itself."""
        if not location.startswith(("https://", "http://")):
            return Path(location)
        if name not in self._downloads:
            if self._folder is None:
                self._folder = Path(tempfile.mkdtemp(prefix="fair2-notebook-"))
            self._folder.mkdir(parents=True, exist_ok=True)
            path = self._folder / str(len(self._downloads))
            urllib.request.urlretrieve(_ascii_url(location), path)
            self._downloads[name] = path
        return self._downloads[name]


def _path(location: str) -> str:
    """The decoded path of a file's location (a URL or a local path)."""
    if location.startswith(("https://", "http://")):
        return unquote(urlparse(location).path)
    return Path(location).as_posix()


def _ascii_url(url: str) -> str:
    """A URL as HTTP sends it: other characters than ASCII percent-encoded ("é" -> "%C3%A9"),
    what is already encoded kept as it is."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=quote(parts.path, safe="/%:@!$&'()*+,;=")))


def _location(url: str, base: str | None) -> str:
    """A file's URL or path, relative ones resolved against the metadata's location."""
    if url.startswith(("https://", "http://")) or base is None:
        return url
    if base.startswith(("https://", "http://")):
        return urljoin(base, url)
    if url.startswith("file://"):
        return unquote(urlparse(url).path)
    return str(Path(base).parent / url)
