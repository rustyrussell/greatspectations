from greatspectations.coverage import LineAnnotation
from greatspectations.report import (
    html_filename,
    render_html,
    render_json,
    render_text,
    status_prefix,
)


def test_status_prefix():
    assert status_prefix(LineAnnotation("f", 1, "x", "gap")) == "***"
    assert status_prefix(LineAnnotation("f", 1, "x", "covered", mentions=1)) == "+  "
    assert status_prefix(LineAnnotation("f", 1, "x", "covered", mentions=2)) == "++ "
    assert status_prefix(LineAnnotation("f", 1, "x", "covered", mentions=3)) == "+++"
    assert status_prefix(LineAnnotation("f", 1, "x", "covered", mentions=7)) == "+++"
    assert status_prefix(LineAnnotation("f", 1, "x", "neutral")) == "   "


def test_render_text():
    by_doc = {
        ("bolt", 11): [
            LineAnnotation("bolt11.md", 5, "A sending node:", "neutral"),
            LineAnnotation("bolt11.md", 6, "- MUST do the thing", "gap"),
            LineAnnotation("bolt11.md", 7, "- MUST do another thing", "covered", mentions=2),
        ],
    }
    lines = render_text(by_doc)
    assert lines == [
        "    bolt11.md:5:A sending node:",
        "*** bolt11.md:6:- MUST do the thing",
        "++  bolt11.md:7:- MUST do another thing",
    ]


def test_render_json_shape():
    by_doc = {
        ("bolt", 11): [LineAnnotation("bolt11.md", 6, "- MUST do it", "gap")],
        ("cmdata-spec", None): [
            LineAnnotation("SPEC.md", 3, "MUST also", "covered", mentions=1),
        ],
    }
    payload = render_json(by_doc, any_uncovered=True)
    assert payload["summary"] == {"any_uncovered": True}
    docs = {d["source"]: d for d in payload["documents"]}
    assert docs["bolt"]["id"] == 11
    assert docs["bolt"]["path"] == "bolt11.md"
    assert docs["bolt"]["lines"] == [
        {"line": 6, "text": "- MUST do it", "status": "gap", "mentions": 0}
    ]
    assert docs["cmdata-spec"]["id"] is None


def test_render_json_empty_document_has_null_path():
    payload = render_json({("bolt", 11): []}, any_uncovered=False)
    assert payload["documents"][0]["path"] is None
    assert payload["documents"][0]["lines"] == []


def test_html_filename():
    assert html_filename("bolt", 11) == "bolt-11.html"
    assert html_filename("cmdata-spec", None) == "cmdata-spec.html"


def test_render_html_escapes_and_colors_status():
    annotations = [
        LineAnnotation("bolt11.md", 6, "<b>- MUST do it</b>", "gap"),
        LineAnnotation("bolt11.md", 7, "- MUST do it twice", "covered", mentions=2),
        LineAnnotation("bolt11.md", 8, "A sending node:", "neutral"),
    ]
    page = render_html(("bolt", 11), "bolt11.md", annotations)
    assert "&lt;b&gt;- MUST do it&lt;/b&gt;" in page
    assert "<script" not in page
    assert 'class="gap"' in page
    assert 'class="covered"' in page
    assert 'class="neutral"' in page
    assert "&times;2" in page
    assert "bolt #11" in page
    assert "bolt11.md" in page
