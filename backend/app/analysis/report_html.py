"""The assessment report as one printable, self-contained HTML document (F6:
"exportable or printable"). The page downloads it as a file, or prints it
(the browser's print dialog also saves it as PDF). A4, always light, no
scripts or outside files; every value is escaped. Sources become numbered
references listed at the end, and a draft is marked "Not yet approved" on
every printed page.
"""

from datetime import datetime
from html import escape

from app.analysis.qa_pairs import DIMENSIONS
from app.core import clock

SECTIONS = (
    ("strengths", "Strengths"),
    ("weaknesses", "Weaknesses"),
    ("gaps", "Evidence gaps"),
    ("verify", "Areas to verify"),
)
STYLE = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { margin: 0; font: 11pt/1.45 "Public Sans", Arial, sans-serif; color: #1A2227; background: #fff; }
header { display: flex; justify-content: space-between; border-bottom: 2px solid #23717A; padding-bottom: 8px; }
.brand { font-weight: 700; color: #23717A; }
.muted { color: #66717A; font-size: 9.5pt; }
h1 { font-size: 18pt; margin: 14px 0 2px; }
h2 { font-size: 12pt; margin: 18px 0 6px; color: #1C5D65; }
.status { display: inline-block; margin-top: 8px; padding: 2px 10px; border-radius: 99px; font-weight: 600; font-size: 9.5pt; }
.approved { background: #E7F3EC; color: #245F3E; }
.draft { background: #FBF0D9; color: #7A5000; }
.position { border: 1px solid #DEE3E6; border-radius: 8px; padding: 10px 14px; margin-top: 14px; }
.position strong { font-size: 14pt; }
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #E9ECEE; vertical-align: top; }
td.num { text-align: right; width: 56px; font-weight: 600; }
ul { margin: 0; padding-left: 18px; }
li { margin: 3px 0; }
.ref { font: 8.5pt "IBM Plex Mono", monospace; color: #23717A; }
.unsupported { color: #932E24; font-size: 9pt; }
.sources li { font-size: 9.5pt; }
footer { margin-top: 22px; border-top: 1px solid #DEE3E6; padding-top: 6px; }
.watermark { position: fixed; top: 0; right: 0; color: #7A5000; font-weight: 700; font-size: 9pt; }
"""


def render_report(
    content: dict,
    *,
    candidate: str,
    job_title: str,
    interview_at: datetime | None,
    duration_minutes: int | None,
    approved_by: str | None,
    approved_at: datetime | None,
) -> str:
    """The whole report as an HTML document (see the module docstring)."""
    approved = approved_at is not None
    references = _references(content)
    interview = (
        f"Interview {clock.local_text(interview_at)}"
        + (f", {duration_minutes} min" if duration_minutes else "")
        if interview_at
        else "Interview"
    )
    status = (
        f'<span class="status approved">Approved by {escape(approved_by or "an interviewer")}, '
        f"{escape(clock.local_text(approved_at))}</span>"
        if approved
        else '<span class="status draft">Not yet approved: draft for review</span>'
    )
    position = content.get("position", {})
    exported = escape(clock.local_text(clock.now()))
    body = [
        (
            '<header><span class="brand">CandiVue AI</span>'
            f'<span class="muted">Assessment report · exported {exported}'
            f" · version {int(content.get('version', 1))}</span></header>"
        ),
        "" if approved else '<div class="watermark">Not yet approved</div>',
        f"<h1>{escape(candidate)}</h1>",
        f'<div class="muted">{escape(job_title)} · {escape(interview)}</div>',
        status,
        (
            '<div class="position"><div class="muted">Overall suitability position</div>'
            f"<strong>{escape(position.get('headline', ''))}</strong>"
            '<div class="muted">A summary for the hiring decision, based on the component '
            "scores below. Not a decision.</div></div>"
        ),
        _scores(content.get("components", {})),
        *(
            _findings(title, content["findings"].get(key, []), references)
            for key, title in SECTIONS
        ),
        _requirements(content.get("requirements", [])),
        _sources(content.get("sources", {}), references),
        '<footer class="muted">'
        + (
            "AI-assisted draft, reviewed and approved by a person."
            if approved
            else "AI-assisted draft, not yet reviewed and approved by a person."
        )
        + " Confidential.</footer>",
    ]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Assessment report · {escape(candidate)}</title>"
        f"<style>{STYLE}</style></head><body>{''.join(body)}</body></html>"
    )


def _references(content: dict) -> dict[str, int]:
    """Each cited source id with its reference number, in order of first use."""
    numbers: dict[str, int] = {}
    for key, _title in SECTIONS:
        for finding in content.get("findings", {}).get(key, []):
            for source_id in finding.get("sources", []):
                numbers.setdefault(source_id, len(numbers) + 1)
    return numbers


def _scores(components: dict) -> str:
    """The component scores table and the requirement coverage line."""
    rows = []
    cv, interview = components.get("cv"), components.get("interview")
    if cv:
        rows.append(("CV screening (overall)", cv["overall"]))
        rows += [(f"CV: {d['label']}", d["score"]) for d in cv["dimensions"].values()]
    if interview:
        rows += [(f"Interview: {name}", interview[name]) for name in DIMENSIONS]
    table = "".join(
        f'<tr><td>{escape(label)}</td><td class="num">{int(score)}</td></tr>'
        for label, score in rows
    )
    coverage = components.get("coverage", {})
    unexplored = coverage.get("unexplored", [])
    line = (
        f"Requirement coverage: {coverage.get('explored', 0)} of {coverage.get('total', 0)} "
        "explored in the interview"
        + (f" (not explored: {escape('; '.join(unexplored))})" if unexplored else "")
    )
    return (
        "<h2>Component scores (0–100)</h2>"
        + (f"<table>{table}</table>" if table else '<p class="muted">No scores.</p>')
        + f'<p class="muted">{line}</p>'
    )


def _findings(title: str, findings: list[dict], references: dict[str, int]) -> str:
    """One section of conclusions, each with its reference numbers."""
    items = []
    for finding in findings:
        refs = " ".join(
            f'<span class="ref">[{references[s]}]</span>' for s in finding["sources"]
        )
        flag = (
            ' <span class="unsupported">No supporting source found: verify before relying on it.</span>'
            if finding.get("unsupported")
            else ""
        )
        items.append(f"<li>{escape(finding['text'])} {refs}{flag}</li>")
    return f"<h2>{title}</h2>" + (
        f"<ul>{''.join(items)}</ul>" if items else '<p class="muted">None noted.</p>'
    )


def _requirements(requirements: list[dict]) -> str:
    """Each job requirement: what CV screening found and where the
    interview explored it."""
    if not requirements:
        return ""
    rows = "".join(
        f"<tr><td>{escape(r['requirement'])}</td><td>{escape(r['level'])}</td>"
        f"<td>{escape(r['cv'] or 'not checked')}</td>"
        f"<td>{escape(', '.join(r['pair_ids']) or 'Never explored')}</td></tr>"
        for r in requirements
    )
    return (
        "<h2>Job requirements</h2><table><tr><th>Requirement</th><th>Level</th>"
        f"<th>CV screening</th><th>Interview</th></tr>{rows}</table>"
    )


def _sources(sources: dict, references: dict[str, int]) -> str:
    """The numbered references: CV excerpts and timestamped transcript lines."""
    if not references:
        return ""
    items = "".join(
        f'<li><span class="ref">[{number}]</span> {escape(sources[source_id]["label"])}: '
        f"“{escape(sources[source_id]['text'])}”</li>"
        for source_id, number in references.items()
        if source_id in sources
    )
    return f'<h2>Sources</h2><ul class="sources">{items}</ul>'
