"""A self-contained private HTML view. No listener, account, CDN or fetch calls."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from html import escape
from importlib.resources import files

from ..branding import logo_uri
from ..jsonio import ContractError
from .cards import encode as encode_session_card
from .cards import project as session_card
from .change_map import render as render_change_map
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
        return f'<div class="passport"><h3>Passport · {e(state)}</h3><p>Add a local Passport to link future sessions to an identity. See Help.</p></div>'
    before = receipt["passport_before"]
    transition = ""
    if before["state"] == "consistent" and (before["passport_id"], before["model_id"]) != (passport["passport_id"], passport["model_id"]):
        transition = f'<p>Previous selected version: <strong>{e(before["version"])}</strong></p><code class="hash">{e(before["passport_id"])}</code><p class="quiet">Selected Passport/model reference changed. This records project history; it does not authenticate continuity of an enrolled agent.</p>'
    return f'<div class="passport"><div class="section-label">AGENT BEING BUILT · DECLARED ASSOCIATION</div><h3>{e(passport["name"])} <span class="version">{e(passport["version"])}</span></h3><p>Passport ID</p><code class="hash">{e(passport["passport_id"])}</code><p class="quiet">Core ID was consistent at capture · model reference: {e(passport["model_reference"])}</p>{transition}</div>'


def activity_block(record, index):
    from ..capture.activity import KINDS, STATES
    activity = record.get('activity', {'state': 'not_enabled', 'events': [], 'truncated': False})
    if activity['state'] == 'not_enabled':
        return '<section class="activity"><h3>Tools &amp; destinations</h3><p class="quiet">Not enabled for this session. <a href="#workflow">Enable local activity for future sessions</a>.</p></section>'
    if activity['state'] == 'unavailable':
        return '<section class="activity"><h3>Tools &amp; destinations</h3><p class="notice">Activity evidence unavailable. Your change receipt is preserved.</p></section>'
    rows = ''.join(f'<li><span>{e(KINDS[item["kind"]])}</span><strong>{e(item["destination"] or "Destination not exposed")}</strong><span>{e(STATES[item["outcome"]])}</span></li>' for item in activity['events'][-8:])
    evidence = (f'<ul class="activity-events">{rows}</ul>' if rows else '<p class="quiet">No supported tool events recorded. This does not mean no network activity occurred.</p>')
    count = len(activity['events'])
    limit = '<p class="notice">128-event limit reached. Activity is incomplete.</p>' if activity['truncated'] else ''
    return f'<section class="activity"><div class="receipt-top"><h3>Tools &amp; destinations</h3><span class="badge">Experimental · partial coverage</span></div><p class="quiet">{count} retained tool events · latest {min(count, 8)} shown</p>{evidence}{limit}<p class="quiet">Reported by your coding tool. These are not verified API requests or a complete browsing history. Hostnames stay local and are excluded from share cards.</p><button class="secondary" data-activity="{index}">Save private activity JSON</button></section>'


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
    warnings = []
    if record["partial"]:
        warnings.append('Some files or settings could not be compared. Counts may be incomplete.')
    if receipt["outcome"] == "recovered":
        warnings.append('The session end was missed. End time and duration are unknown.')
    if evolution["status"] != "consistent" or not record["change_count_complete"]:
        warnings.append('Some history evidence is unavailable. Your saved receipt is preserved.')
    if evolution["earlier_history_gap"]:
        warnings.append('Earlier history has a gap; continuity across it is unknown.')
    warning = ''.join(f'<p class="notice" role="status">{e(message)}</p>' for message in warnings)
    preview = change_list(record["changes"][:5])
    more = len(record["changes"]) - 5
    if more > 0:
        preview += f'<p class="quiet">{more} more in Details</p>'
    saved_at = datetime.fromisoformat(record["local_finished_at"]).strftime('%d %b %Y · %H:%M').lstrip('0')
    between = f'<div><strong>{record["between_count"]}</strong><span>between sessions</span></div>' if record['between_count'] else ''
    passport = receipt.get('passport_after')
    identity = ''
    if passport and passport['state'] == 'consistent':
        identity = f'<p class="identity-summary">{e(passport["name"])} · v{e(passport["version"])} <span>Passport {e(passport["passport_id"][:12])}…</span></p>'
    history = 'Linked to previous session' if evolution['previous_session_id'] and evolution['status'] == 'consistent' else 'First recorded session' if evolution['event_sequence'] == 1 else 'Session saved'
    return f'''<article class="receipt" data-index="{index}">
<div class="receipt-top"><span class="section-label">{e(saved_at)}</span><span class="badge">{"Partial coverage" if record["partial"] else "Saved"}</span></div>
<h2>{e(TOOL_NAMES[receipt["tool"]])} <span>· {e(duration(receipt["elapsed_ms"]))}</span></h2>
<div class="receipt-numbers"><div><strong>{len(receipt["file_changes"])}</strong><span>files changed</span></div><div><strong>{record["during_count"]}</strong><span>meaningful changes</span></div>{between}</div>
{render_change_map(record) if index == 0 else ''}
{warning}<div class="change-preview">{preview}</div>{identity}<p class="quiet history-link">{history}</p>
{activity_block(record, index)}
<details class="receipt-detail"><summary>Details</summary>
<p class="quiet">{e("Hook-reported tool" if receipt["tool_basis"] == "hook_reported" else "Selected by you")} · {e(receipt["capture_mode"].replace('_', ' '))} capture · elapsed time includes idle/sleep.</p>
{revision}
<div class="detail-grid"><section><h3>What changed during the session?</h3>{change_list(record["changes"])}<p class="quiet">{"Some supporting details or counts are unavailable; no reconstruction percentage is claimed." if not record["change_count_complete"] else "Recorded counts are retained even if some supporting details become unavailable." if evolution["status"] != "consistent" else "Counts group related declarations within this interval."}</p></section><section>{passport_block(receipt)}<div class="trace"><h3>{"A complete local trace" if trace else "Trace needs more evidence"}</h3><p>{record["reconstructable_changes"]} of {record["during_count"]} session events have a checked Passport + session + before/after revision trace.</p><p class="quiet">{e(record["trace"].replace("_", " "))}. Unsigned local evidence; runtime use and authorship are unverified.</p></div></section></div>
<details><summary>Changes between captures ({record["between_count"]})</summary><p class="quiet">These edits have no known coding-session attribution. Comparison: {e(record["between_comparison"].replace("_", " "))}.</p>{change_list(record["between_changes"])}</details>
<details><summary>Previous-session comparison</summary>{comparison}</details>
<details><summary>All file changes ({len(receipt["file_changes"])})</summary><ul class="file-list">{files_list}</ul><p class="quiet">{receipt["unknown_count"]} known paths could not be compared. {receipt["excluded_after"]} paths excluded at the ending capture.</p></details>
<details><summary>Coverage, session and version evidence</summary><p>Session <code class="hash">{e(receipt["session_id"])}</code></p><p>Local project <code>{e(receipt["project_id"])}</code></p><p>Outcome: {e(receipt["outcome"].replace("_", " "))}</p><p class="quiet">Configured MCP/tools/models are declarations. Their actual runtime use is unknown. Observed revision hashes are separate from Core Passport versions.</p>{coverage}<p>Before revision <code class="hash">{e(before or "Unavailable")}</code></p><p>After revision <code class="hash">{e(after or "Unavailable")}</code></p></details>
<div class="actions"><button class="secondary" data-receipt="{index}">Save private receipt JSON</button></div>
</details></article>'''


def render(report, *, native=False):
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
    active = "".join(f'<p class="notice">{e(TOOL_NAMES[s["tool"]])} session in progress. A receipt will appear after its end is captured. <a href="#workflow">Help</a></p>' for s in report["active_sessions"])
    methods = "".join(f'<p><strong>{e(key.replace("_", " ").capitalize())}.</strong> {e(value)}</p>' for key, value in report["methodology"].items())
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'">
<title>Forkit · your private session history</title><link rel="icon" href="data:,"><style>{styles}</style></head>
<body><a class="skip" href="#main">Skip to receipts</a><div class="shell"><aside><div class="brand"><img class="brand-logo" src="{logo_uri()}" alt="Forkit AI"><span class="oss">OSS</span></div><p class="section-label">LOCAL SESSION MEMORY</p><nav aria-label="Receipt views"><button data-view="latest" aria-pressed="true">Latest session <span>↗</span></button><button data-view="today" aria-pressed="false">Today</button><button data-view="week" aria-pressed="false">This week</button><button data-view="history" aria-pressed="false">History</button></nav><div class="local-note"><strong>No account. No uploads.</strong><p>Your receipts stay on your device.</p><a href="#workflow">Help</a><a href="#methodology">How counts work</a></div></aside>
<main id="main"><header><div><div class="eyebrow">SESSION RECEIPT</div><h1>What changed?</h1></div><span class="local-badge">● Local only</span></header>
<div class="context"><span>{report["project_count"]} local project{"s" if report["project_count"] != 1 else ""} · {report["total_receipts"]} saved receipt{"s" if report["total_receipts"] != 1 else ""}</span><span>{e(report["timezone"])}</span></div>
<div class="snapshot-refresh"><span>Saved view · {e(report["generated_at"])} · new receipts require reopening</span><code>~/.local/bin/forkit-radar open</code></div>
{active}<section class="metrics" aria-label="Selected view summary"><div><span>Sessions</span><strong id="metric-receipts">{report["total_receipts"]}</strong></div><div><span>Files changed</span><strong id="metric-files">{report["periods"]["history"]["file_changes"]}</strong></div><div><span>Meaningful changes</span><strong id="metric-changes">{report["periods"]["history"]["meaningful_changes"]}</strong></div></section>
<div class="view-heading"><div><h2 id="view-title">Latest session</h2><p class="quiet" id="view-description"></p></div><button id="share" class="primary" type="button">Share card</button></div>
<p id="share-status" class="quiet" role="status" aria-live="polite">Counts only. Saved locally.</p>
<p id="coverage-note" class="notice" hidden></p>
<label class="search" for="search">Search history <input id="search" type="search" placeholder="Tool, file, dependency or Passport" autocomplete="off"></label>
<p class="quiet" id="shown">Showing the latest {report["displayed_receipts"]} of {report["total_receipts"]} receipts.</p><div id="receipts">{content}</div>
<section id="empty" class="empty" {"hidden" if report["records"] else ""}><div class="empty-mark">⌁</div><h2>No receipts in this view yet.</h2><p id="empty-description">Finish a coding session, then reopen Forkit.</p><a href="#workflow">Help</a></section>
<details id="workflow" class="help"><summary>Help</summary><p>Open Forkit again to refresh this saved view. Automatic capture uses your coding tool's session hooks in local Git projects. Open the actual repository in your coding tool: a parent folder containing repositories is not captured. Start a new session after setup; existing conversations have no retroactive baseline.</p><p>Optional local tool activity for future sessions (review changed hooks in your coding tool):</p><pre>~/.local/bin/forkit-radar setup --activity
# Stop future activity collection:
~/.local/bin/forkit-radar setup --no-activity</pre><p>Experimental supported tool events only. Codex hosted WebSearch, hidden API calls inside scripts and personal browser history are not observed. No queries, URL paths, headers, prompts or results are stored. Activity is a private annotation; it is excluded from change totals, share cards and public reporting.</p><p>Manual fallback:</p><pre>forkit-radar session start --tool cursor
# Work in your editor, then use the returned session ID:
forkit-radar session stop &lt;session-id&gt;
forkit-radar view --output next-private-view.html</pre><p>Command wrapper:</p><pre>forkit-radar session run --tool codex -- codex</pre><p>Missing session end? Check <code>forkit-radar session active</code>, then use <code>forkit-radar session recover &lt;id&gt;</code> after stopping work. Its end time stays unknown.</p><p>Local Passport: use <code>forkit-radar passport create --help</code> with your own metadata. Select it when starting capture with <code>--registry /your/local/registry --passport-id &lt;actual-agent-id&gt;</code>.</p><p>Search filters the shown timeline; daily/weekly totals include all retained receipts. For more entries use <code>view --limit 1000</code>. Local dates use {e(report["timezone"])}.</p></details>
<details id="methodology" class="help"><summary>About these receipts</summary>{methods}</details>
<footer><span>You vibe code. Forkit remembers.</span><span>Saved view · reopen Forkit to refresh</span></footer>
<noscript><p>All shown receipts remain readable without JavaScript. Filtering and local downloads require it. CLI summary-card and receipt --json work independently.</p></noscript>
</main></div><script type="application/json" id="report">{payload}</script><script type="application/json" id="cards">{json.dumps(cards)}</script><script>{script}</script></body></html>'''
    if native:
        start = page.index('<details id="workflow"')
        end = page.index('<details id="methodology"', start)
        page = page[:start] + '''<details id="workflow" class="help"><summary>Help</summary>
<p>Capture sets up or pauses your coding tools. Codex requires a one-time review in /hooks.</p>
<p>History refreshes when new receipts arrive. Refresh checks again now. Passport optionally links future sessions to a local identity.</p>
<p>If a tool closed without saving a receipt, use Recover session after work has stopped. Its ending time stays unknown.</p>
<p>Share card exports counts; receipt JSON includes private filenames. Nothing is uploaded.</p></details>''' + page[end:]
        page = page.replace('Saved view · reopen Forkit to refresh', 'Local history · refreshes when receipts arrive')
        page = page.replace(f'<div class="snapshot-refresh"><span>Saved view · {e(report["generated_at"])} · new receipts require reopening</span><code>~/.local/bin/forkit-radar open</code></div>', '')
        page = page.replace('<body>', '<body data-native="true">', 1)
    raw = page.encode()
    if len(raw) > MAX_VIEW_BYTES:
        raise ContractError("private_view_size_limit_reduce_display_limit")
    return raw
