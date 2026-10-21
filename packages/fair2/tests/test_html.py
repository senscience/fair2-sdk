import dataclasses

import fair2
from fair2.card import Link


def summary(title, text):
    """The title of a folded part of the card."""
    return (
        f'<summary><span class="fair2-section">{title}</span>'
        f' <span class="fair2-summary">({text})</span></summary>'
    )


def test_texts_of_the_metadata_are_escaped(db):
    html = fair2.card(db).html()
    assert "<h2>Test &lt;dataset&gt;</h2>" in html
    assert "Test score &lt;0-10&gt;" in html
    assert "<dataset>" not in html


def test_links_and_sections(db):
    html = fair2.card(db).html()
    assert '<a href="https://doi.org/10.71728/senscience.test-0001"' in html
    assert ">CC BY 4.0</a>" in html
    assert "<tr><th>Croissant metadata</th><td>/" in html
    # Two paragraphs in the description.
    assert "<p>A small dataset for the tests.</p><p>Second paragraph.</p>" in html
    # The parts of the card are folded, with a summary of their content. Responsible use has none:
    # its sections are the labels inside.
    assert '<details><summary><span class="fair2-section">Responsible use</span></summary>' in html
    assert summary("Record sets", "4 record sets, 2 with a DuckDB table") in html
    assert summary("Fields", "8 fields") in html
    assert summary("Other files", "1 file not in a record set") in html
    # And one folded table of fields per record set, with the shape of the table.
    assert html.count("<details") == 4 + 4
    assert "<strong>participants</strong> (4 rows × 4 fields)" in html


def test_statistics_are_shown(db):
    html = fair2.card(db).html()
    assert "1 (25.0%)" in html  # the missing age
    assert "28 – 45" in html
    assert "2 distinct" in html
    assert "2.5 MB" in html  # size of notes.xlsx
    assert "none: unsupported format" in html


def test_is_displayed_by_jupyter(db):
    card = fair2.card(db)
    assert card._repr_html_() == card.html()
    assert repr(card) == "<DatasetCard 'Test <dataset>': 4 record sets>"


def test_the_frontiers_theme_by_default(db):
    html = fair2.card(db).html()
    assert '<div class="fair2-card fair2-themed" id="fair2-card-' in html
    # The notebooks show the logo at their top, not in the card.
    assert "<svg" not in html
    assert '[data-jp-theme-light="false"] .fair2-card' in html
    assert '<span class="fair2-badge">Version 1.2.0</span>' in html


def test_without_a_theme(db):
    html = fair2.card(db, theme=None).html()
    assert '<div class="fair2-card" id="fair2-card-' in html
    assert "<svg" not in html
    assert "--f2-" not in html


def test_a_custom_theme(db):
    theme = fair2.Theme(
        light={"link": "#123456"}, dark={"link": "#abcdef"}, logo="<svg></svg>", logo_label="Lab"
    )
    html = fair2.card(db, theme=theme).html()
    assert ".fair2-card.fair2-themed { --f2-link: #123456; }" in html
    assert 'aria-label="Lab"><svg></svg></div>' in html


def test_only_http_urls_are_links(db):
    card = dataclasses.replace(
        fair2.card(db), data_article=Link('Click "here"', "javascript:alert(1)")
    )
    html = card.html()
    assert "javascript:" not in html
    assert "<td>Click &#34;here&#34;</td>" in html


def test_most_frequent_values_only_where_the_metadata_has_statistics(db):
    html = fair2.card(db).html()
    assert "<td>Lausanne (2), New York (1), Geneva (1)</td>" in html
    # One column header: only participants has statistics.
    assert html.count("<th>Most frequent values</th>") == 1


def test_the_search_box_is_made_by_its_script(db):
    html = fair2.card(db).html()
    # No box in the HTML: where the script doesn't run, there is none that would do nothing.
    assert "<input" not in html.split("<script>")[0]
    assert "box.innerHTML" in html
    # What the script filters, in each searchable part.
    assert html.count("<details data-fair2-section>") == 3
    assert html.count('<tr data-fair2-row="record-set">') == 4
    assert html.count("<tr data-fair2-field>") == 8
    assert html.count('<tr data-fair2-row="file">') == 1
    # Each card has its own id, which its script looks for.
    other = fair2.card(db).html()
    card_id = html.split('id="', 1)[1].split('"', 1)[0]
    assert card_id.startswith("fair2-card-") and card_id not in other
    assert f'const CARD_ID = "{card_id}";' in html
