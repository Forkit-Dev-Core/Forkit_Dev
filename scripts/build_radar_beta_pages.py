"""Build the offline, account-free Session Receipt guide."""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

VERSION = "0.1.0b3"

ROOT = Path(__file__).resolve().parents[1] / "packages/radar/beta-kit"
CSS = """*{box-sizing:border-box}body{margin:0;background:#faf7ef;color:#29175f;font:16px/1.55 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:30px 20px 60px}nav{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid #dcd5c8;padding-bottom:18px}a{color:#006f74}h1{font-size:clamp(32px,5vw,52px);line-height:1.12;letter-spacing:-1.5px}h2{font-size:25px;line-height:1.25}h3{margin:0 0 8px}.badge,.notice{background:#e2f1ec;color:#07575b;padding:12px 18px;border-radius:12px}.badge{display:inline-block;margin-top:28px;font-weight:700;font-size:13px}section,details{margin-top:24px;padding:24px;border:1px solid #dcd5c8;border-radius:18px;background:#fffdfa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#211738;color:#f0edfa;border-radius:12px;padding:18px;font-size:14px}button,.button{display:inline-block;border:1px solid #c9bfdb;background:#29175f;color:white;padding:11px 18px;border-radius:10px;font:inherit;font-weight:650;cursor:pointer;text-decoration:none}button:disabled{opacity:.55;cursor:default}button.secondary{background:#fff;color:#29175f}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #007f80;outline-offset:4px}label{display:block;font-weight:600;margin-bottom:5px}select,input[type=text]{display:block;width:100%;padding:10px;border:1px solid #bfb5cf;border-radius:8px;background:#fff;color:#29175f;font:inherit}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.check{display:flex;gap:10px;align-items:start;font-weight:400}.check input{margin-top:6px}fieldset{border:0;margin:0;padding:0}legend{font-weight:700;padding-bottom:10px}summary{cursor:pointer;font-weight:700}.quiet{color:#605572;font-size:14px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid #ddd;vertical-align:top}#feedback-status,#copy-status{min-height:28px}footer{margin-top:35px;color:#605572}.actions{display:flex;flex-wrap:wrap;gap:10px}[hidden]{display:none!important}@media(max-width:600px){.grid{grid-template-columns:1fr}section,details{padding:18px}main{padding:20px 12px}nav{flex-direction:column}}"""
COPY_JS = """document.querySelectorAll('[data-copy]').forEach(button=>button.addEventListener('click',async()=>{const target=document.getElementById(button.dataset.copy);try{await navigator.clipboard.writeText(target.textContent);document.getElementById('copy-status').textContent='Copied. Review the command before running it in Terminal.';}catch{const range=document.createRange();range.selectNodeContents(target);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);document.getElementById('copy-status').textContent='Command selected. Use your browser’s Copy action.';}}));"""
GUIDE = """<nav><strong>Forkit Dev / Session Receipt</strong><a href="USAGE.md">Optional usage counts</a></nav>
<div class="badge">OPEN-SOURCE BETA · VERSION</div><h1>You vibe code.<br>Forkit remembers what changed.</h1><p>A short local trial. No Forkit signup or login. Uploads are off by default.</p>
<div class="notice">This kit has been tested locally. Outside-user validation is still pending. It contains no real adoption numbers.</div>
<section><h2>1. Install from this extracted kit</h2><p>Open Terminal in the extracted <code>forkit-session-receipt</code> folder. Check the exact platform and Python version in README.txt.</p>
<pre id="preflight">sh install.sh --check</pre><button data-copy="preflight">Copy prerequisite check</button>
<pre id="install">sh install.sh</pre><button data-copy="install">Copy install command</button>
<p>On macOS, <code>Install.command</code> is an optional Terminal launcher. This is an unsigned script, not a notarized Mac app. If macOS blocks it, use the Terminal command after reviewing the kit. No security settings need to be disabled.</p>
<p>The installer chooses a compatible Python already on your PATH, keeps dependencies isolated, and prints the exact command path. It never replaces an existing installation or changes shell profiles. Source checkout alternative: <code>sh scripts/install_radar.sh</code>.</p>
<details><summary>Missing Python, Git, or an earlier Forkit installation?</summary>
<p>macOS: install a matching Python from <a href="https://www.python.org/downloads/macos/" rel="noreferrer">Python.org</a>. Git is available with Apple's Command Line Tools. Ubuntu: install Git and the Python venv package matching this kit, then retry. Installing prerequisites may need internet and administrator access; Forkit itself needs no account.</p>
<p>Keep the same Python minor version as the bundle. A Python 3.11 kit will not install into Python 3.12. This kit does not bundle Python or Git. Broader architecture/Windows support has not been validated.</p>
<p>If an old installation exists, keep it and its history. Install this candidate into separate new application and command directories:</p><pre>sh install.sh --prefix "$HOME/.local/share/forkit-radar-beta1" --bin-dir "$HOME/.local/bin/forkit-beta1"</pre>
<p>Use the full command path the installer prints. Every command below uses the default <code>~/.local/bin/forkit-radar</code>; substitute your printed path for a custom installation. No automatic upgrade runs.</p></details></section>
<section><h2>2. Capture your first real coding session</h2><p>In Terminal, go to the root of your existing Git project. Do not initialize an unrelated parent folder.</p>
<pre id="doctor">~/.local/bin/forkit-radar doctor</pre><button data-copy="doctor">Copy local setup check</button>
<h3>Automatic official hooks</h3><pre id="hooks">~/.local/bin/forkit-radar hooks setup --agent codex</pre><button data-copy="hooks">Copy hook setup</button><p>Restart Codex and review the project hooks with <code>/hooks</code>. Existing configuration is never overwritten: use <code>hooks print</code> to review and merge entries. See <a href="CAPTURE.md">CAPTURE.md</a> for exact coverage and recovery. Claude Code and Cursor adapters are separate and experimental.</p>
<p>Codex captures a conversation lifecycle, not each reply. Desktop completion can wait until archive/app exit or 30 minutes idle without an open client. Cursor's fire-and-forget start makes its capture partial. Use a wrapper when a precise command boundary matters.</p>
<h3>Wrapper fallback</h3><pre id="cli">~/.local/bin/forkit-radar session run --tool codex -- codex</pre><button data-copy="cli">Copy Codex wrapper</button><pre>~/.local/bin/forkit-radar session run --tool claude-code -- claude</pre><p>The receipt appears when the wrapped command exits. Your coding tool may need its own account or network; Forkit does not.</p>
<details><summary>Manual fallback for editors</summary><pre id="start">~/.local/bin/forkit-radar start --tool cursor</pre><button data-copy="start">Copy editor start</button><p>Work in your editor, then return to the same Git root:</p><pre id="stop">~/.local/bin/forkit-radar stop</pre><button data-copy="stop">Copy stop and receipt</button><p>Use the same <code>--store</code> if selected. One capture can be active per project. Missing end event: <code>session active</code>, then <code>session recover ID</code>; recovery explicitly has an unknown end.</p></details>
</section>
<section><h2>3. Inspect, return, and share if useful</h2><pre id="review">~/.local/bin/forkit-radar receipt --files
~/.local/bin/forkit-radar history
~/.local/bin/forkit-radar summary --period week
~/.local/bin/forkit-radar view --output session-history.html
~/.local/bin/forkit-radar card --output receipt-card.html</pre><button data-copy="review">Copy review commands</button>
<p>Open the HTML files locally. Your private history shows the captured changes; the share card contains counts and fixed labels. The card can save a PNG in your browser. Use a new output filename if one already exists.</p>
<p>On another day, start and stop a second real session in the same project. Look for what changed since the previous session. Official hooks capture later sessions when enabled; no persistent Forkit daemon is installed.</p>
<details><summary>What the receipt can and cannot establish</summary><p>It compares supported Git-project files and declared dependencies/MCP/tool/model settings. Duration is the captured interval. Human edits during that interval can be included; unsupported or inaccessible data stays unknown.</p><p>Tool identity is your selection or a lifecycle-hook report. Runtime models and AI authorship are not authenticated. An optional Passport association uses existing Core identity. Missing Passport details remain unknown. Local history links do not authenticate an agent across revisions.</p><p>You can create a local Passport without signup using <code>forkit-radar passport create</code> with your real required metadata. It is optional for the first receipt. See <code>passport create --help</code> and <code>session start --help</code> for explicit Core association.</p></details>
</section>
<details><summary>Optional guided example without an AI service</summary><p>This creates a new isolated sample project and separate private history. It is a demonstration, not AI output or a real-user activation. Run from a writable folder; it refuses an existing sample project.</p>
<pre id="guided">(
set -eu
FORKIT_TRIAL_ROOT=$(pwd -P)
mkdir -m 700 forkit-guided-example
cd forkit-guided-example
git init -q
printf 'message = "before"\\n' &gt; app.py
~/.local/bin/forkit-radar start --tool other --store "$FORKIT_TRIAL_ROOT/forkit-guided-history"
printf 'message = "after"\\n' &gt; app.py
~/.local/bin/forkit-radar stop --store "$FORKIT_TRIAL_ROOT/forkit-guided-history"
)</pre><button data-copy="guided">Copy isolated example</button>
<p>No model, agent or identity is invented for this example. Use it only with reporting disabled, or with a validation profile.</p></details>
<section><h2>4. Keep using it; choose whether to contribute counts</h2><p>No questionnaire or Forkit account is required. Your history and share cards remain local.</p><pre>~/.local/bin/forkit-radar usage policy
~/.local/bin/forkit-radar usage status</pre><p>After your first receipt, new explicit consent can enable optional count-only reports during normal use, at most once per 24 hours. The public collector is not deployed with this bundle. Do not enable test/example sessions as community adoption. There is no automatic transfer of earlier Footprints or manual reporting consent.</p><p>Inspect counts with <code>usage preview</code>, stop with <code>usage disable</code>, or remove a sent contribution with <code>usage withdraw</code>. Enabling requires an explicit endpoint and policy choice; read USAGE.md first.</p></section>
<details><summary>Keep your data, remove or change the application</summary><p>Close any wrapped session first. The installer prints its application and command locations. Removing those application files does not require deleting your session data. Preserve <code>~/.forkit-radar</code> and your existing Core registry. Back up a private store using <code>storage backup --output /new/private/backup.sqlite3</code> before a later version change.</p><p>Application virtual environments depend on the original Python installation and location; do not move them. The installer refuses overwrites. Count reporting stays off until new explicit consent.</p></details>
<div id="copy-status" role="status" aria-live="polite"></div><footer>Local-first by default. Tested bundle targets: macOS Apple Silicon / Python 3.11 and Linux x86_64 / Python 3.12. Platform prerequisites still apply.</footer>"""


def page(title, body, script):
    def digest(value):
        return base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()

    csp = f"default-src 'none'; style-src 'sha256-{digest(CSS)}'; script-src 'sha256-{digest(script)}'; connect-src 'none'; img-src data: blob:; base-uri 'none'; form-action 'none'; object-src 'none'"
    return f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{csp}"><title>{title}</title><style>{CSS}</style></head><body><main>{body}</main><script>{script}</script></body></html>\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents = {
        "START_HERE.html": page(
            "Forkit Session Receipt — start here", GUIDE.replace("VERSION", VERSION), COPY_JS
        )
    }
    site = ROOT.parent / "site/beta"
    if not args.check:
        site.mkdir(exist_ok=True)
    for name, text in documents.items():
        if args.check:
            if (ROOT / name).read_text() != text or (site / name).read_text() != text:
                raise SystemExit("Beta page drift: " + name)
        else:
            (ROOT / name).write_text(text)
            (site / name).write_text(text)
    print("Beta pages match" if args.check else "Beta pages built")


if __name__ == "__main__":
    main()
