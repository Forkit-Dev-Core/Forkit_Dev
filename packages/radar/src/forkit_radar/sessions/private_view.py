"""A self-contained private HTML view. No listener, account, CDN or fetch calls."""

from __future__ import annotations

import base64
import hashlib
import json
from html import escape
from importlib.resources import files

from ..jsonio import ContractError
from .cards import encode as encode_session_card
from .cards import project as session_card
from .cli import duration
from .details import ReceiptV2
from .models import TOOL_NAMES, Receipt
from .summary_cards import encode as encode_summary_card
from .summary_cards import project as summary_card

MAX_VIEW_BYTES = 16_777_216


def e(value):
    return escape(str(value), quote=True)


def change_list(events):
    output = []
    for change in events:
        detail = change["file"]
        info = ""
        if detail:
            info = f'<span class="change-detail">{e(detail["kind"].replace("_", " "))}'
            if detail["previous_path"]:
                info += f' · from {e(detail["previous_path"])}'
            info += "</span>"
        for item in change["details"]:
            before = item["before"] if item["before"] is not None else "absent"
            after = item["after"] if item["after"] is not None else "absent"
            info += f'<span class="change-detail">{e(before)} → {e(after)} <span class="source">{e(item["source"])}</span></span>'
        if change["category"] == "passport":
            info += '<span class="change-detail">Declared selection changed. Agent continuity is unproven.</span>'
        output.append(f'<li><span class="kind">{e(change["category"])}</span><div><strong>{e(change["label"])}</strong>{info}</div></li>')
    return '<ul class="changes">' + "".join(output) + "</ul>" if output else '<p class="quiet">No supported changes recorded in this interval.</p>'


def passport_block(receipt):
    passport = receipt.get("passport_after")
    if not passport or passport["state"] != "consistent":
        state = passport["state"].replace("_", " ") if passport else "not captured"
        return f'<div class="passport"><h3>Passport · {e(state)}</h3><p>Your receipt is saved. A selected, consistent local Passport adds an identity reference to future traces.</p><p class="quiet">Local Passport creation needs no Forkit account. See the local workflow below.</p></div>'
    before = receipt["passport_before"]
    transition = ""
    if before["state"] == "consistent" and (before["passport_id"], before["model_id"]) != (passport["passport_id"], passport["model_id"]):
        transition = f'<p>Previous selected version: <strong>{e(before["version"])}</strong></p><code class="hash">{e(before["passport_id"])}</code><p class="quiet">Selected Passport/model reference changed. This records project history; it does not authenticate continuity of an enrolled agent.</p>'
    return f'<div class="passport"><div class="section-label">AGENT BEING BUILT · DECLARED ASSOCIATION</div><h3>{e(passport["name"])} <span class="version">{e(passport["version"])}</span></h3><p>Passport ID</p><code class="hash">{e(passport["passport_id"])}</code><p class="quiet">Core ID was consistent at capture · model reference: {e(passport["model_reference"])}</p>{transition}</div>'


def article(record, index):
    receipt, evolution = record["receipt"], record["evolution"]
    trace = record["trace"] == "complete"
    before, after = evolution["before_revision"], evolution["after_revision"]
    if evolution["status"] == "consistent":
        revision = f'<div class="revision"><span>Observed revision</span><code>{e(before[:12])}</code><span aria-label="to">→</span><code>{e(after[:12])}</code><span>{"unchanged scoped state" if before == after else "new scoped state"}</span></div>'
    else:
        revision = f'<p class="notice">Evolution evidence {e(evolution["status"])} · {e(evolution["reason"].replace("_", " "))}. The saved receipt remains available.</p>'
    if evolution["earlier_history_gap"]:
        revision += '<p class="notice">Earlier project history uses a different scope or lacks an evolution link. This boundary is not a proven continuation.</p>'
    prior = receipt.get("since_previous")
    comparison = '<p class="quiet">No earlier comparable receipt was retained.</p>'
    if prior and prior["baseline_session_id"]:
        comparison = f'<p>Since comparable receipt <code>{e(prior["baseline_session_id"])}</code>: {len(prior["file_changes"])} file changes · {len(prior["metadata"]["changes"])} metadata entries · {e(prior["comparison"])}.</p><p class="quiet">{prior["skipped_sessions"]} newer unsuitable baselines skipped. This wider comparison is not added again to the meaningful-change total.</p>'
    files_list = "".join(f'<li><code>{e(f["path"])}</code><span>{e(f["kind"].replace("_", " "))}</span></li>' for f in receipt["file_changes"])
    coverage = ""
    if receipt.get("metadata"):
        coverage = '<ul class="coverage">' + "".join(f'<li><span>{e(c["source"])}</span><strong>{e(c["comparison"])}</strong><span>{e(c["before"])} → {e(c["after"])}</span></li>' for c in receipt["metadata"]["coverage"]) + "</ul>"
    return f'''<article class="receipt" data-index="{index}">
<div class="receipt-top"><span class="section-label">SESSION RECEIPT</span><span class="badge">{"Partial coverage" if record["partial"] else "Scoped capture complete"}</span></div>
<h2>{e(TOOL_NAMES[receipt["tool"]])} <span>· {e(duration(receipt["elapsed_ms"]))}</span></h2>
<p class="quiet">{e("Hook-reported tool" if receipt["tool_basis"] == "hook_reported" else "Selected by you")} · {e(receipt["capture_mode"])} capture · {e(record["local_finished_at"].replace("T", " "))}</p>
<div class="receipt-numbers"><div><strong>{len(receipt["file_changes"])}</strong><span>file changes</span></div><div><strong>{record["during_count"]}</strong><span>meaningful events during session</span></div><div><strong>{record["between_count"]}</strong><span>events between captures</span></div></div>
{revision}
<details class="receipt-detail" {"open" if index == 0 else ""}><summary>Explore this receipt</summary>
<div class="detail-grid"><section><h3>What changed during the session?</h3>{change_list(record["changes"])}<p class="quiet">{"Some supporting details or counts are unavailable; no reconstruction percentage is claimed." if not record["change_count_complete"] else "Recorded counts are retained even if some supporting details become unavailable." if evolution["status"] != "consistent" else "Counts group related declarations within this interval."}</p></section><section>{passport_block(receipt)}<div class="trace"><h3>{"A complete local trace" if trace else "Trace needs more evidence"}</h3><p>{record["reconstructable_changes"]} of {record["during_count"]} session events have a checked Passport + session + before/after revision trace.</p><p class="quiet">{e(record["trace"].replace("_", " "))}. Unsigned local evidence; runtime use and authorship are unverified.</p></div></section></div>
<details><summary>Changes between captures ({record["between_count"]})</summary><p class="quiet">These edits have no known coding-session attribution. Comparison: {e(record["between_comparison"].replace("_", " "))}.</p>{change_list(record["between_changes"])}</details>
<details><summary>Previous-session comparison</summary>{comparison}</details>
<details><summary>All file changes ({len(receipt["file_changes"])})</summary><ul class="file-list">{files_list}</ul><p class="quiet">{receipt["unknown_count"]} known paths could not be compared. {receipt["excluded_after"]} paths excluded at the ending capture.</p></details>
<details><summary>Coverage, session and version evidence</summary><p>Session <code class="hash">{e(receipt["session_id"])}</code></p><p>Local project <code>{e(receipt["project_id"])}</code></p><p>Outcome: {e(receipt["outcome"].replace("_", " "))}</p><p class="quiet">Configured MCP/tools/models are declarations. Their actual runtime use is unknown. Observed revision hashes are separate from Core Passport versions.</p>{coverage}<p>Before revision <code class="hash">{e(before or "Unavailable")}</code></p><p>After revision <code class="hash">{e(after or "Unavailable")}</code></p></details>
<div class="actions"><button class="secondary" data-receipt="{index}">Save private receipt JSON</button></div>
</details></article>'''


def render(report):
    styles = files("forkit_radar.sessions").joinpath("view.css").read_text()
    script = files("forkit_radar.sessions").joinpath("view.js").read_text()
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    payload = json.dumps(report, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    cards = {period: base64.b64encode(encode_summary_card(summary_card(report, period), ".html")).decode() for period in ("today", "week")}
    if report["records"]:
        raw = report["records"][0]["receipt"]
        receipt = (ReceiptV2 if raw["schema_version"] == "2.0" else Receipt).model_validate(raw)
        cards["latest"] = base64.b64encode(encode_session_card(session_card(receipt), ".html")).decode()
    content = "".join(article(record, i) for i, record in enumerate(report["records"]))
    active = "".join(f'<p class="notice">Active local session · {e(TOOL_NAMES[s["tool"]])} · <code>{e(s["session_id"])}</code>. Finish capture to generate its receipt.</p>' for s in report["active_sessions"])
    methods = "".join(f'<p><strong>{e(key.replace("_", " ").capitalize())}.</strong> {e(value)}</p>' for key, value in report["methodology"].items())
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'">
<title>Forkit · your private session history</title><link rel="icon" href="data:,"><style>{styles}</style></head>
<body><a class="skip" href="#main">Skip to receipts</a><div class="shell"><aside><div class="brand"><span class="mark">#</span> Forkit<span class="oss">OSS</span></div><p class="section-label">LOCAL SESSION MEMORY</p><nav aria-label="Receipt views"><button data-view="latest" aria-pressed="true">Latest session <span>↗</span></button><button data-view="today" aria-pressed="false">Today</button><button data-view="week" aria-pressed="false">This week</button><button data-view="history" aria-pressed="false">History</button></nav><div class="local-note"><strong>Yours, locally.</strong><p>No account. No uploads.<br>Your project details stay here.</p><a href="#workflow">Local workflow</a><a href="#methodology">How counts work</a></div></aside>
<main id="main"><header><div><div class="eyebrow">PRIVATE VIEW · LOCAL OSS</div><h1>What changed?</h1><p class="lead">Your AI sessions. Your system’s recorded evolution.</p></div><span class="local-badge">● Local only</span></header>
<div class="context"><span>{report["project_count"]} local project{"s" if report["project_count"] != 1 else ""} · {report["total_receipts"]} saved receipts</span><span>{e(report["timezone"])}</span></div>
{active}<section class="metrics" aria-label="Selected view summary"><div><span>Session receipts</span><strong id="metric-receipts">{report["total_receipts"]}</strong></div><div><span>Meaningful change events</span><strong id="metric-changes">{report["periods"]["history"]["meaningful_changes"]}</strong></div><div><span>Changes with a local trace</span><strong id="metric-traces">{report["periods"]["history"]["reconstructable_changes"]}</strong></div><div><span>Receipts with partial coverage</span><strong id="metric-partial">{report["periods"]["history"]["partial_receipts"]}</strong></div></section>
<div class="view-heading"><div><h2 id="view-title">Latest session</h2><p class="quiet" id="view-description">Captured changes and declared metadata.</p></div><button id="share" class="primary" type="button">Save aggregate share card</button></div>
<p id="share-status" class="quiet" role="status" aria-live="polite">A share card contains only counts and fixed labels. This private page contains your project details.</p>
<label class="search" for="search">Find in shown receipts <input id="search" type="search" placeholder="Tool, dependency, file or Passport" autocomplete="off"></label>
<p class="quiet" id="shown">Timeline contains the latest {report["displayed_receipts"]} of {report["total_receipts"]} retained receipts. Day/week totals use all retained receipts.</p><div id="receipts">{content}</div>
<section id="empty" class="empty" {"hidden" if report["records"] else ""}><div class="empty-mark">⌁</div><h2>No receipts in this view yet.</h2><p>Capture a local session, then generate this view again. Your first result needs no Forkit account.</p><a href="#workflow">See the local workflow ↓</a></section>
<details id="workflow" class="help"><summary>Local workflow</summary><p>From your selected Git project, start a session around your editor:</p><pre>forkit-radar session start --tool cursor
# Work in your editor, then use the returned session ID:
forkit-radar session stop &lt;session-id&gt;
forkit-radar view --output next-private-view.html</pre><p>For a command-line coding tool:</p><pre>forkit-radar session run --tool codex -- codex</pre><p>Select an existing local Core Passport when starting capture with <code>--registry /your/local/registry --passport-id &lt;actual-agent-id&gt;</code>. Create one with the existing <code>forkit-radar passport create --help</code> workflow using your real metadata. No account is required.</p><p>This is a saved local view. Generate a new file after another session to refresh it; existing files are never overwritten. For more timeline entries use <code>--limit 1000</code>; to select a local project use <code>--project-id &lt;id&gt;</code>.</p></details>
<details id="methodology" class="help"><summary>What these records establish</summary>{methods}</details>
<footer><span>You vibe code. Forkit remembers.</span><span>Generated {e(report["generated_at"])} · private local file</span></footer>
<noscript><p>All shown receipts remain readable without JavaScript. Filtering and local downloads require it. CLI summary-card and receipt --json work independently.</p></noscript>
</main></div><script type="application/json" id="report">{payload}</script><script type="application/json" id="cards">{json.dumps(cards)}</script><script>{script}</script></body></html>'''
    raw = page.encode()
    if len(raw) > MAX_VIEW_BYTES:
        raise ContractError("private_view_size_limit_reduce_display_limit")
    return raw
