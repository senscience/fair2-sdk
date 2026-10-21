"""HTML rendering of a dataset card, for Jupyter.

The markup is the Jinja template `templates/card.html.j2`, the styles `assets/card.css` and, with a
theme, `assets/card-themed.css`. The template is autoescaped: every text of the metadata is escaped,
and only http(s) URLs become links.

Styles are scoped to the card. Without a theme, they only set the layout, and the card follows the
notebook's look. With a theme (`fair2.themes`), the card has its logo, colours and typeface, in
light and dark notebooks. Where styles are removed (GitHub's notebook viewer), the card is still
readable as plain HTML.
"""

from __future__ import annotations

import datetime
import decimal
import functools

import jinja2
from markupsafe import Markup

from fair2.card import ColumnStats, DatasetCard, Link
from fair2.themes import Theme, asset


def render(card: DatasetCard, theme: Theme | None = None) -> str:
    style = asset("card.css")
    if theme is not None:
        style = f"{style}\n{asset('card-themed.css')}\n{theme.css()}"
    return _template().render(
        card=card,
        theme=theme,
        style=Markup(style),
        card_id=card.id,
        script=Markup(asset("card-search.js")),
        badges=_badges(card),
        about=_about(card),
    )


@functools.cache
def _template() -> jinja2.Template:
    environment = jinja2.Environment(
        loader=jinja2.PackageLoader("fair2", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=jinja2.StrictUndefined,
    )
    environment.filters.update(
        number=_number,
        size=_size,
        missing=_missing,
        value_range=_range,
        plural=_plural,
        top_values=_top_values,
    )
    environment.tests["link"] = lambda value: isinstance(value, Link)
    return environment.get_template("card.html.j2")


def _badges(card: DatasetCard) -> list[tuple[str, Link | str]]:
    """(prefix, value) of the badges under the title: DOI, version, publication date, license."""
    badges = []
    if card.doi:
        badges.append(("DOI ", Link(card.doi, f"https://doi.org/{card.doi}")))
    elif card.url:
        badges.append(("", Link(card.url, card.url)))
    if card.version:
        badges.append(("Version ", card.version))
    if card.date_published:
        badges.append(("Published ", card.date_published))
    if card.license:
        badges.append(("License ", card.license))
    return badges


def _about(card: DatasetCard) -> list[tuple[str, Link | str]]:
    """(label, value) of the rows of the table under the description, when they have a value."""
    rows = [
        ("Authors", ", ".join(card.authors)),
        ("Data article", card.data_article),
        # The landing page, when the badges link the DOI.
        ("Data portal", Link(card.url, card.url) if card.doi and card.url else None),
        ("Croissant metadata", card.source),
        ("Cite as", card.cite_as),
        ("Keywords", ", ".join(card.keywords)),
        ("Spatial coverage", "; ".join(card.spatial_coverage)),
        ("Temporal coverage", "; ".join(card.temporal_coverage)),
        ("Funding", ", ".join(card.funders)),
    ]
    return [(label, value) for label, value in rows if value]


def _plural(count: int, word: str) -> str:
    """ "1 file", "2 files"."""
    return f"{count:,} {word}{'s' if count != 1 else ''}"


def _top_values(values: list[tuple[str, int]], limit: int = 5) -> str:
    """ "N (15), F (14), L (10), V (8), G (8), …"."""
    text = ", ".join(f"{value} ({_number(count)})" for value, count in values[:limit])
    return f"{text}, …" if len(values) > limit else text


def _missing(stats: ColumnStats | None, rows: int | None) -> str:
    missing = stats.missing if stats else None
    if missing is None:
        return ""
    if missing and rows:
        return f"{_number(missing)} ({missing / rows:.1%})"
    return _number(missing)


def _range(stats: ColumnStats | None) -> str:
    """The min and max of numbers and dates, or the number of distinct values."""
    if stats is None:
        return ""
    if stats.minimum is not None or stats.maximum is not None:
        return f"{_value(stats.minimum)} – {_value(stats.maximum)}"
    if stats.distinct is not None:
        return f"{_number(stats.distinct)} distinct"
    return ""


def _value(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return str(value) if value is not None else ""
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, (float, decimal.Decimal)):
        return f"{float(value):,.4g}"
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)


def _number(value: int | None) -> str:
    return f"{value:,}" if value is not None else ""


def _size(size: int | str | None) -> str:
    """A size in bytes, in B, kB, MB... A contentSize that isn't a number of bytes, as it is."""
    if size is None:
        return ""
    if isinstance(size, str):
        return size
    if size < 1000:
        return f"{size:,} B"
    for unit in ("kB", "MB", "GB", "TB"):
        size /= 1000
        if size < 1000 or unit == "TB":
            return f"{size:.1f} {unit}"
