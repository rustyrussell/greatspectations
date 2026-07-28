"""Render coverage annotations (see coverage.build_annotations) as text,
JSON, or one self-contained HTML page per document.

Text/JSON share one status-per-line model: "gap" (should be covered,
isn't), "covered" (with a mention count), "neutral" (not expected to be
a requirement). Text uses a 3-character prefix per line: '***' for a
gap, '+'/'++'/'+++' for 1/2/3-or-more mentions, three spaces for
neutral. HTML colors the same three states (red/green/plain) so the
same information reads at a glance.
"""

import html as html_lib
import os
from typing import Dict, List, Optional, Tuple

from greatspectations.coverage import DocKey, LineAnnotation

_MAX_MENTION_MARKS = 3


def status_prefix(annotation: LineAnnotation) -> str:
    """The 3-character text-mode prefix for one annotated line."""
    if annotation.status == "gap":
        return "***"
    if annotation.status == "covered":
        return ("+" * min(annotation.mentions, _MAX_MENTION_MARKS)).ljust(3)
    return "   "


def render_text(by_doc: Dict[DocKey, List[LineAnnotation]]) -> List[str]:
    """One '{prefix} {file}:{line}:{text}' string per annotated line,
    across every document in by_doc, in order.
    """
    return [
        "{} {}:{}:{}".format(status_prefix(a), a.file, a.line, a.text)
        for annotations in by_doc.values()
        for a in annotations
    ]


def render_json(
    by_doc: Dict[DocKey, List[LineAnnotation]], any_uncovered: bool
) -> dict:
    documents = []
    for (source, id_value), annotations in by_doc.items():
        documents.append({
            "source": source,
            "id": id_value,
            "path": annotations[0].file if annotations else None,
            "lines": [
                {
                    "line": a.line, "text": a.text,
                    "status": a.status, "mentions": a.mentions,
                }
                for a in annotations
            ],
        })
    return {"documents": documents, "summary": {"any_uncovered": any_uncovered}}


def html_filename(source: str, id_value: Optional[object]) -> str:
    """Filename for one document's HTML report (source[-id].html)."""
    return "{}.html".format(source) if id_value is None else "{}-{}.html".format(source, id_value)


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #ffffff; --fg: #1a1a1a; --muted: #767676;
  --gap-bg: #ffe0e0; --gap-fg: #8a1f1f;
  --covered-bg: #e1f5e6; --covered-fg: #1f6b34;
  --border: #ddd;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1e1e1e; --fg: #e6e6e6; --muted: #9a9a9a;
    --gap-bg: #4a1f1f; --gap-fg: #ff9b9b;
    --covered-bg: #1f3d28; --covered-fg: #8ce0a4;
    --border: #444;
  }}
}}
body {{
  background: var(--bg); color: var(--fg); margin: 0;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
}}
h1 {{
  font-size: 1rem; padding: 0.75rem 1rem; margin: 0;
  border-bottom: 1px solid var(--border);
  font-family: system-ui, sans-serif;
}}
.legend {{
  padding: 0.5rem 1rem; font-size: 0.85rem; color: var(--muted);
  font-family: system-ui, sans-serif;
}}
.legend .sw {{ padding: 0 0.3rem; border-radius: 3px; }}
.legend .gap {{ background: var(--gap-bg); color: var(--gap-fg); }}
.legend .covered {{ background: var(--covered-bg); color: var(--covered-fg); }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
td {{ padding: 0 0.5rem; white-space: pre-wrap; word-break: break-word; vertical-align: top; }}
td.lineno {{ color: var(--muted); text-align: right; user-select: none; }}
tr.gap td.text {{ background: var(--gap-bg); color: var(--gap-fg); }}
tr.covered td.text {{ background: var(--covered-bg); color: var(--covered-fg); }}
.mentions {{ color: var(--muted); font-size: 0.75rem; padding-left: 0.5rem; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="legend">
<span class="sw gap">red</span> should be covered but isn't &middot;
<span class="sw covered">green</span> covered (&times;N shown when quoted more than once) &middot;
plain = not expected to be a requirement
</div>
<table>
{rows}
</table>
</body>
</html>
"""


def render_html(
    doc_key: Tuple[str, Optional[object]], path: str, annotations: List[LineAnnotation]
) -> str:
    """One self-contained HTML page annotating a single document."""
    source, id_value = doc_key
    doc_label = "{} #{}".format(source, id_value) if id_value is not None else source
    heading = "{} — {}".format(doc_label, os.path.basename(path))

    rows = []
    for a in annotations:
        text = html_lib.escape(a.text, quote=False) or "&nbsp;"
        badge = ""
        if a.status == "covered" and a.mentions > 1:
            badge = ' <span class="mentions">&times;{}</span>'.format(a.mentions)
        rows.append(
            '<tr class="{}"><td class="lineno">{}</td>'
            '<td class="text">{}{}</td></tr>'.format(a.status, a.line, text, badge)
        )

    return _HTML_TEMPLATE.format(
        title=html_lib.escape(heading, quote=False), rows="\n".join(rows),
    )
