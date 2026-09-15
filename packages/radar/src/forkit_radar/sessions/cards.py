"""Explicit public projection: only fixed labels and aggregate counts cross here.

Never serialize a private receipt and then redact it. HTML, SVG and JSON are
rendered from this independent strict contract, with no identifiers/free text.
"""

from __future__ import annotations

import base64
import hashlib
from html import escape
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..branding import card_logo
from ..contracts import Contract, Counter
from ..identity.storage import canonical
from .details import ReceiptV2
from .models import TOOL_NAMES, Receipt, Tool

State = Literal["complete", "partial", "not_captured"]
Count = Annotated[int, Field(ge=0, le=4096)]


class Counts(Contract):
    state: State
    added: Count | None = None
    removed: Count | None = None
    changed: Count | None = None

    @model_validator(mode="after")
    def availability(self):
        values = (self.added, self.removed, self.changed)
        if self.state == "not_captured":
            if any(v is not None for v in values):
                raise ValueError("uncaptured_counts")
        elif any(v is None for v in values) or sum(values) > 4096:
            raise ValueError("invalid_counts")
        return self


class Prior(Contract):
    state: Literal["complete", "partial", "no_baseline", "not_captured"]
    files: Count | None = None
    metadata_entries: Count | None = None
    skipped_receipts: Counter = 0

    @model_validator(mode="after")
    def availability(self):
        if self.state in {"not_captured", "no_baseline"}:
            if self.files is not None or self.metadata_entries is not None:
                raise ValueError("unavailable_comparison_counts")
        elif self.files is None or self.metadata_entries is None:
            raise ValueError("missing_comparison_counts")
        return self


class SessionCard(Contract):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["forkit_session_card"] = "forkit_session_card"
    privacy: Literal["aggregate_only"] = "aggregate_only"
    tool: Tool
    tool_basis: Literal["user_selected", "hook_reported"] = "user_selected"
    elapsed_minutes: Counter | None
    outcome: Literal[
        "manual_stop", "hook_end", "command_exited", "command_failed", "launch_failed", "interrupted", "recovered"
    ]
    file_state: Literal["complete", "partial"]
    file_changes: Annotated[int, Field(ge=0, le=4000)]
    possible_renames: Annotated[int, Field(ge=0, le=2000)]
    dependencies: Counts
    tools: Counts
    models: Counts
    configuration: Counts
    passport: Literal["not_captured", "not_selected", "consistent", "unavailable", "conflicted"]
    passport_change: Literal["not_captured", "not_selected", "unchanged", "changed", "unknown"]
    since_previous: Prior
    between_sessions: Prior
    attribution: Literal["observed_interval_not_proven_authorship"] = "observed_interval_not_proven_authorship"
    runtime: Literal["not_observed"] = "not_observed"

    @model_validator(mode="after")
    def consistency(self):
        if self.possible_renames > self.file_changes:
            raise ValueError("invalid_rename_count")
        if self.outcome == "recovered" and (
            self.elapsed_minutes is not None or self.file_state != "partial"
        ):
            raise ValueError("recovery_interval_unknown")
        return self


def project(receipt: Receipt) -> SessionCard:
    # Revalidate even model_construct/model_copy inputs before any public output.
    receipt = (ReceiptV2 if isinstance(receipt, ReceiptV2) else Receipt).model_validate(receipt)
    details = isinstance(receipt, ReceiptV2)

    def counts(category):
        if not details:
            return Counts(state="not_captured")
        changes = [c for c in receipt.metadata.changes if c.category == category]
        coverage = [c for c in receipt.metadata.coverage if c.category == category]
        if not coverage:
            return Counts(state="not_captured")
        return Counts(
            state=receipt.metadata.status(category),
            added=sum(c.kind == "added" for c in changes),
            removed=sum(c.kind == "removed" for c in changes),
            changed=sum(c.kind == "changed" for c in changes),
        )

    def previous(comparison):
        if comparison.comparison == "no_baseline":
            return Prior(state="no_baseline", skipped_receipts=comparison.skipped_sessions)
        return Prior(
            state=comparison.comparison,
            files=len(comparison.file_changes),
            metadata_entries=len(comparison.metadata.changes),
            skipped_receipts=comparison.skipped_sessions,
        )

    return SessionCard(
        tool=receipt.tool,
        tool_basis=receipt.tool_basis,
        elapsed_minutes=None if receipt.elapsed_ms is None else receipt.elapsed_ms // 60000,
        outcome=receipt.outcome,
        file_state=receipt.comparison,
        file_changes=len(receipt.file_changes),
        possible_renames=sum(c.kind == "possible_rename" for c in receipt.file_changes),
        dependencies=counts("dependencies"), tools=counts("tools"),
        models=counts("models"), configuration=counts("configuration"),
        passport=receipt.passport_after.state if details else "not_captured",
        passport_change=receipt.metadata.passport_change if details else "not_captured",
        since_previous=previous(receipt.since_previous) if details else Prior(state="not_captured"),
        between_sessions=previous(receipt.between_sessions) if details else Prior(state="not_captured"),
    )


def count_text(counts: Counts) -> str:
    if counts.state == "not_captured":
        return "Not captured"
    return (
        f"+{counts.added} / −{counts.removed} / ~{counts.changed}"
        + (" · partial" if counts.state == "partial" else "")
    )


def prior_text(prior: Prior) -> str:
    if prior.state == "not_captured":
        return "Not captured in this legacy receipt"
    if prior.state == "no_baseline":
        return "No comparable baseline available"
    return (
        f"{'At least ' if prior.state == 'partial' else ''}{prior.files} {'file' if prior.files == 1 else 'files'} · "
        f"{prior.metadata_entries} metadata {'entry' if prior.metadata_entries == 1 else 'entries'}"
        + (" · partial" if prior.state == "partial" else "")
    )


def svg(card: SessionCard) -> str:
    card = SessionCard.model_validate(card)
    description = (
        f"{TOOL_NAMES[card.tool]}, {'reported by its hook' if card.tool_basis == 'hook_reported' else 'selected by the user'}. "
        f"{'At least ' if card.file_state == 'partial' else ''}{card.file_changes} supported file {'change' if card.file_changes == 1 else 'changes'}. "
        f"Dependency entries {count_text(card.dependencies)}. MCP/tool entries {count_text(card.tools)}. "
        f"Model entries {count_text(card.models)}. Configuration entries {count_text(card.configuration)}. "
        f"Since comparable receipt: {prior_text(card.since_previous)}. "
        "Observed interval and declared metadata; runtime and authorship unverified."
    )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title description">',
        '<title id="title">Forkit Session Receipt · aggregate share card</title>',
        f'<desc id="description">{escape(description)}</desc>',
        '<rect width="1200" height="630" rx="28" fill="#F4EFE5"/>',
        '<rect x="34" y="34" width="1132" height="496" rx="22" fill="#17122E"/>',
        '<path d="M34 95 H1166" stroke="#3E2C74"/>',
    ]

    def text(x, y, value, size=22, color="#EDEAF8", weight=400):
        parts.append(
            f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">{escape(value)}</text>'
        )

    text(65, 73, "FORKIT SESSION RECEIPT", 22, "#5AD8D2", 700)
    parts.append(card_logo())
    elapsed = (
        "duration unknown" if card.elapsed_minutes is None
        else "under 1 min" if card.elapsed_minutes == 0
        else f"{card.elapsed_minutes} min"
    )
    # Display huge (valid) intervals compactly without changing the JSON count.
    if card.elapsed_minutes is not None and card.elapsed_minutes > 99999:
        elapsed = "over 99,999 min"
    text(65, 143, f"{TOOL_NAMES[card.tool]} · {elapsed}", 29, weight=700)
    text(65, 175, "Hook-reported tool · observed interval" if card.tool_basis == "hook_reported" else "Tool selected by user · observed interval", 17, "#C2BAD8")
    text(65, 237, f"{'At least ' if card.file_state == 'partial' else ''}{card.file_changes} file {'change' if card.file_changes == 1 else 'changes'}", 38, weight=700)
    qualifier = f"Supported files · {card.file_state} capture"
    if card.possible_renames:
        qualifier += f" · {card.possible_renames} possible renames"
    text(65, 269, qualifier, 17, "#C2BAD8")
    for i, (label, counts) in enumerate((
        ("Dependencies", card.dependencies), ("MCP / tools", card.tools),
        ("Models", card.models), ("Configuration", card.configuration),
    )):
        y = 326 + i * 43
        text(65, y, label, 20, "#C2BAD8")
        text(265, y, count_text(counts), 19, "#5AD8D2")
    text(65, 507, "Declared entries: + added / − removed / ~ changed", 16, "#C2BAD8")
    text(675, 220, "SINCE COMPARABLE RECEIPT", 17, "#5AD8D2", 700)
    text(675, 253, prior_text(card.since_previous), 16)
    text(675, 293, "BETWEEN SESSIONS", 17, "#5AD8D2", 700)
    text(675, 326, prior_text(card.between_sessions), 16)
    if card.since_previous.skipped_receipts:
        text(675, 356, "Newer unsuitable baselines skipped", 16, "#C2BAD8")
    passport = {
        "not_captured": "Passport: not captured", "not_selected": "Passport: not selected",
        "consistent": "Passport: Core ID consistent", "unavailable": "Passport: unavailable",
        "conflicted": "Passport: conflicted",
    }[card.passport]
    text(675, 397, passport, 19)
    text(675, 427, "Declared association · ID stays private" if card.passport == "consistent"
         else "Optional local identity · no account", 16, "#C2BAD8")
    if card.passport_change in {"changed", "unknown"}:
        text(675, 455, f"Passport change: {card.passport_change}", 16, "#FFCB75")
    outcome = {
        "manual_stop": "Manually stopped", "command_exited": "Command exited successfully",
        "hook_end": "Session ended · reported by tool hook",
        "command_failed": "Command failed", "launch_failed": "Command could not launch",
        "interrupted": "Session interrupted", "recovered": "Recovered · end time unknown",
    }[card.outcome]
    text(675, 499, outcome, 17, "#FFCB75")
    text(38, 569, "You vibe code. Forkit remembers.", 26, "#27185F", 700)
    footer = (
        "Includes interval until recovery. Runtime / authorship unverified."
        if card.outcome == "recovered" else
        "Counts only. No project names, paths or IDs. Runtime / authorship unverified."
    )
    text(38, 605, footer, 18, "#3E2C74")
    parts.append("</svg>")
    return "\n".join(parts)


SCRIPT = """const status = document.getElementById('status');
function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = name;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
document.getElementById('png').addEventListener('click', async () => {
  const button = document.getElementById('png'); button.disabled = true;
  const node = document.querySelector('svg');
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(node)], {type:'image/svg+xml'}));
  try {
    const image = new Image(); image.src = url; await image.decode();
    const canvas = document.createElement('canvas'); canvas.width = 1200; canvas.height = 630;
    canvas.getContext('2d').drawImage(image, 0, 0);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('PNG unavailable');
    save(blob, 'forkit-session-receipt.png'); status.textContent = 'PNG saved locally. Nothing uploaded.';
  } catch { status.textContent = 'PNG export unavailable in this browser. Save the SVG instead.'; }
  finally { URL.revokeObjectURL(url); button.disabled = false; }
});
document.getElementById('svg').addEventListener('click', () => {
  save(new Blob([new XMLSerializer().serializeToString(document.querySelector('svg'))], {type:'image/svg+xml'}), 'forkit-session-receipt.svg');
  status.textContent = 'SVG saved locally. Nothing uploaded.';
});"""


def html(card: SessionCard) -> str:
    drawing = svg(card)
    digest = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; img-src blob: data:; style-src 'unsafe-inline'; script-src 'sha256-{digest}'">
<title>Forkit · local share card</title><link rel="icon" href="data:,">
<style>body{{margin:0;background:#F4EFE5;color:#27185F;font:17px system-ui,sans-serif;padding:32px}}main{{max-width:1200px;margin:auto}}h1{{font-size:28px}}svg{{width:100%;height:auto;display:block}}button{{font:inherit;border:2px solid #27185F;border-radius:9px;padding:12px 20px;background:#27185F;color:#fff;cursor:pointer}}button:focus-visible{{outline:3px solid #0A7E84;outline-offset:4px}}.actions{{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}}p{{line-height:1.5}}@media(max-width:600px){{body{{padding:16px}}}}</style></head>
<body><main><h1>Your local share card</h1><p>Review before sharing. This card contains only counts and fixed labels. Detailed receipts and Passport IDs stay private. No upload or account.</p>
{drawing}
<div class="actions"><button id="png" type="button">Save PNG</button><button id="svg" type="button">Save SVG</button></div>
<p id="status" role="status" aria-live="polite">1200 × 630 · generated locally · sharing is your choice</p>
<p>Metadata counts are declaration entries, not unique installed packages or confirmed tool use. Partial captures are lower bounds. A comparable baseline may skip newer incomplete receipts; no baseline means unknown.</p>
<noscript>PNG export needs browser JavaScript. Generate an SVG directly with the card command instead.</noscript>
</main><script>{SCRIPT}</script></body></html>'''


def encode(card: SessionCard, format: str) -> bytes:
    card = SessionCard.model_validate(card)
    if format == ".json":
        return canonical(card) + b"\n"
    if format == ".svg":
        return svg(card).encode()
    if format == ".html":
        return html(card).encode()
    raise ValueError("card_format_requires_html_svg_or_json")
