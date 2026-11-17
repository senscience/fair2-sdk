import dataclasses
import re

import pytest
from markdown_it import MarkdownIt

import fair2_notebook
from fair2_notebook.card import Link

# CommonMark, HTML included, as notebook frontends render Markdown cells
MARKDOWN = MarkdownIt("commonmark", {"html": True})


@pytest.fixture
def card(dataset):
    return fair2_notebook.card(dataset)


def labels(html):
    """The small headers of the parts, in order."""
    return re.findall(r"text-transform: uppercase;[^>]*>([^<]+)</div>", html)


def test_the_parts_in_order(card):
    html = card.top_html()
    assert html.startswith('<div style="background: #ffffff;')
    assert "<h1 " in html and ">Test &lt;dataset&gt;</h1>" in html
    assert labels(html) == [
        "Description",
        "Authors",
        "Data article",
        "Keywords",
        "Cite as",
        "Spatial coverage",
        "Temporal coverage",
        "Responsible use",
    ]


def test_inline_styles_only(card):
    # No stylesheet or script: JupyterLab keeps inline styles in Markdown cells, trusted or not
    html = card.top_html()
    assert "<style" not in html and "<script" not in html and "class=" not in html
    assert html.count('style="') > 30


def test_one_html_block_in_a_markdown_cell(card):
    # A blank line would end the HTML, and the rest would be read as Markdown
    card = dataclasses.replace(
        card, description="First.\n\n\n\nSecond *not emphasis*.", cite_as="A.\n\nB."
    )
    html = card.top_html()
    assert "\n\n" not in html
    tokens = MARKDOWN.parse(html)
    assert [t.type for t in tokens] == ["html_block"]


def test_badges_description_and_details(card):
    html = card.top_html()
    doi = "10.71728/senscience.test-0001"
    assert f'DOI <a href="https://doi.org/{doi}" target="_blank"' in html
    assert ">Version 1.2.0</span>" in html
    # Two paragraphs in the description
    assert ">A small dataset for the tests.</p><p " in html and ">Second paragraph.</p>" in html
    # The authors, linked to their ORCID when they have one
    assert '<a href="https://orcid.org/0000-0002-1825-0097" target="_blank"' in html
    assert ">Ada Lovelace</a>, Grace Hopper</div>" in html
    assert ">memory, attention, students</div>" in html
    # Only the content of the responsible use is folded: its summary lists its sections
    assert ">Intended uses, Limitations, Biases, Data collection</summary>" in html


def test_the_intro_after_the_name(card):
    html = card.top_html(intro='This notebook <a href="https://example.org">reproduces</a>.')
    assert '</h1><p style="margin: 0 0 0.8em; font-style: italic;' in html
    assert 'This notebook <a href="https://example.org">reproduces</a>.</p>' in html
    assert "font-style: italic" not in card.top_html()


def test_texts_of_the_metadata_are_escaped(card):
    html = dataclasses.replace(
        card, description="<script>alert(1)</script> & <b>x</b>", keywords=["<i>k</i>"]
    ).top_html()
    assert "<script" not in html and "<b>" not in html and "<i>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;x&lt;/b&gt;" in html


def test_only_http_urls_are_links(card):
    html = dataclasses.replace(card, data_article=Link("Click", "javascript:alert(1)")).top_html()
    assert "javascript:" not in html


def test_line_breaks_in_texts(card):
    html = dataclasses.replace(card, cite_as="Lovelace, A.\nTest dataset.").top_html()
    assert "Lovelace, A.<br>Test dataset.</div>" in html


def test_without_details(card):
    # Parts without content are left out, their headers too
    bare = dataclasses.replace(
        card,
        description=None,
        authors=[],
        data_article=None,
        keywords=[],
        cite_as=None,
        spatial_coverage=[],
        temporal_coverage=[],
        funders=[],
        responsible_use=[],
    )
    html = bare.top_html()
    assert labels(html) == []
    assert "display: grid" not in html


def test_colours_from_the_theme(card):
    theme = fair2_notebook.Theme(
        light={**fair2_notebook.FRONTIERS.light, "link": "#123456"}, dark={}, font=None
    )
    html = dataclasses.replace(card, theme=theme).top_html()
    assert "color: #123456" in html and "font-family" not in html
    # Frontiers by default, also without a theme
    assert dataclasses.replace(card, theme=None).top_html() == card.top_html()
