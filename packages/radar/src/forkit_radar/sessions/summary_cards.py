"""Separate allowlisted summary card contract. No private view is serialized."""

from __future__ import annotations

import base64
import hashlib
from html import escape
from typing import Literal

from pydantic import model_validator

from ..branding import card_logo
from ..contracts import Contract, Counter
from ..identity.storage import canonical
from .cards import SCRIPT
from .meaningful import CATEGORIES, POLICY, ChangeCounts


class SummaryCard(Contract):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["forkit_summary_card"] = "forkit_summary_card"
    privacy: Literal["aggregate_only"] = "aggregate_only"
    counting_policy: Literal["session-meaningful-changes-v1"] = POLICY
    period: Literal["today", "week"]
    receipts: Counter
    meaningful_changes: Counter
    during_session_changes: Counter
    between_session_changes: Counter
    reconstructable_changes: Counter
    partial_receipts: Counter
    incomplete_history_receipts: Counter
    categories: ChangeCounts
    attribution: Literal["observed_intervals_not_proven_authorship"] = "observed_intervals_not_proven_authorship"
    evidence: Literal["unsigned_local_history_declared_passports"] = "unsigned_local_history_declared_passports"

    @model_validator(mode="after")
    def consistent(self):
        if (
            self.meaningful_changes != self.during_session_changes + self.between_session_changes
            or sum(self.categories.model_dump().values()) != self.meaningful_changes
            or self.reconstructable_changes > self.during_session_changes
            or self.partial_receipts > self.receipts
            or self.incomplete_history_receipts > self.receipts
            or not self.receipts and self.meaningful_changes
        ):
            raise ValueError("inconsistent_summary_counts")
        return self


def project(report, period="today"):
    stats = report["periods"][period]
    # Explicit projection; arbitrary keys, strings, names, IDs and paths cannot
    # flow through from the private report into this independent contract.
    return SummaryCard(
        period=period,
        receipts=stats["receipts"], meaningful_changes=stats["meaningful_changes"],
        during_session_changes=stats["during_session_changes"],
        between_session_changes=stats["between_session_changes"],
        reconstructable_changes=stats["reconstructable_changes"],
        partial_receipts=stats["partial_receipts"],
        incomplete_history_receipts=stats["incomplete_history_receipts"],
        categories=ChangeCounts(**{k: stats["categories"][k] for k in CATEGORIES}),
    )


def svg(card):
    card = SummaryCard.model_validate(card)
    def number(value):
        return f"{value:,}" if value <= 999_999 else "999,999+"
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title description">', '<title id="title">Forkit local summary</title>', '<desc id="description">Aggregate counts of recorded changes. Local history with declared Passport associations; AI authorship and runtime use are unverified.</desc>', '<rect width="1200" height="630" rx="28" fill="#F4EFE5"/>', '<rect x="32" y="32" width="1136" height="487" rx="22" fill="#17122E"/>']
    def text(x, y, value, size=22, color="#EDEAF8", weight=400):
        parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">{escape(str(value))}</text>')
    text(65, 78, "FORKIT · " + ("TODAY" if card.period == "today" else "THIS WEEK"), 22, "#5AD8D2", 700)
    parts.append(card_logo())
    text(65, 159, number(card.meaningful_changes), 66, weight=700)
    text(65, 198, "meaningful change events", 25)
    text(65, 237, f"{number(card.receipts)} saved session receipts", 22, "#C2BAD8")
    text(650, 132, "PRESERVED CONTEXT", 18, "#5AD8D2", 700)
    ratio = "History incomplete" if card.incomplete_history_receipts else "No changes yet" if not card.meaningful_changes else f"{number(card.reconstructable_changes)} / {number(card.meaningful_changes)}"
    text(650, 184, ratio, 35, weight=700)
    text(650, 224, "with a Passport + session + revision trace", 17, "#C2BAD8")
    text(65, 295, f"{number(card.during_session_changes)} during sessions · {number(card.between_session_changes)} between captures", 20, "#5AD8D2")
    names = {"files": "Files", "dependencies": "Dependencies", "tools": "MCP / tools", "models": "Models", "configuration": "Settings", "passport": "Passport references"}
    for i, (key, value) in enumerate(card.categories.model_dump().items()):
        x, y = (65 if i < 3 else 650), 345 + (i % 3) * 42
        text(x, y, f"{names[key]}  {number(value)}", 22)
    text(65, 487, f"{number(card.partial_receipts)} receipts with partial coverage · counts follow a scoped policy", 17, "#FFCB75")
    text(38, 565, "You vibe code. Forkit remembers.", 29, "#27185F", 700)
    text(38, 602, "Local history · runtime/authorship unverified · github.com/Forkit-Dev-Core/Forkit_Dev", 16, "#3E2C74")
    return "\n".join(parts + ["</svg>"])


def encode(card, format):
    card = SummaryCard.model_validate(card)
    if format == ".json":
        return canonical(card) + b"\n"
    drawing = svg(card)
    if format == ".svg":
        return drawing.encode()
    if format != ".html":
        raise ValueError("card_format_requires_html_svg_or_json")
    script = SCRIPT.replace("forkit-session-receipt", "forkit-summary")
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; img-src blob: data:; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'">
<title>Forkit · local summary card</title><link rel="icon" href="data:,"><style>body{{margin:0;padding:32px;background:#F4EFE5;color:#27185F;font:17px system-ui}}main{{max-width:1200px;margin:auto}}svg{{width:100%;height:auto}}button{{font:inherit;background:#27185F;color:white;padding:12px 20px;border:0;border-radius:9px;cursor:pointer;margin:20px 8px 0 0}}button:focus-visible{{outline:3px solid #0A7E84;outline-offset:4px}}p{{line-height:1.6}}@media(max-width:600px){{body{{padding:16px}}}}</style></head>
<body><main><h1>Your local summary card</h1><p>Counts and fixed labels only. No project names, filenames, dependency names, dates or Passport IDs. Review before sharing.</p>{drawing}<button id="png" type="button">Save PNG</button><button id="svg" type="button">Save SVG</button><p id="status" role="status" aria-live="polite">1200 × 630 · generated locally · nothing uploaded</p><p>Meaningful changes follow a documented counting policy. Between-session changes have unknown session attribution. Traces check unsigned local records and declared Passport associations. Partial coverage excludes unknown edits; it does not establish complete system visibility.</p><noscript>Use the summary-card command with an SVG output when JavaScript is unavailable.</noscript></main><script>{script}</script></body></html>'''.encode()
