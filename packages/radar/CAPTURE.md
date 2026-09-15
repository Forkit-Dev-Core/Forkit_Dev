# Automatic session capture

Forkit works locally without a Forkit account. It observes changes inside a chosen Git root; it does not authenticate who authored each edit. Keep one active capture per project, or use separate worktrees for concurrent agents.

## 1. Install once: user-level automatic capture (b4 candidate)

The b4 installer runs `forkit-radar setup` after installation. It detects supported
CLI commands and existing allowlisted macOS application metadata without launching
an agent. It configures detected tools once, without connecting repositories:

```sh
forkit-radar setup --status
forkit-radar open
```

On macOS the installer also creates a local Finder launcher in
`~/Applications/Forkit Session Receipt.app`. Open it after coding to generate fresh
private history. This launcher is not a signed, self-contained macOS distribution;
the installed Python environment is still required. See [MACOS.md](MACOS.md).

User hooks live in `~/.codex/hooks.json`, `~/.claude/settings.json` and
`~/.cursor/hooks.json`. Explicit `CODEX_HOME` and `CLAUDE_CONFIG_DIR` overrides are
respected. Existing JSON settings and other hooks are preserved, with private
backups before replacement. Malformed, unsupported, oversized or unsafe settings
are left for review. Setup does not change tool policies or disableAllHooks.
Codex still requires review/trust of the exact new definitions in `/hooks`.
Restart the coding tool and start a new session; an already-open session has no
retroactive baseline. Changed definitions need tool review again.

The event's reported working directory selects its nearest physical Git root.
Root/home directories and broad personal folders are refused; symlinked paths,
non-Git chats and unsupported remote/background workspaces are not captured.
There is no scan of home, project registration, process polling, startup daemon,
cloud signup, invented Passport or AI-authorship claim. Separate projects share
local history while retaining distinct project identity. One active capture per
Git root remains the limit; simultaneous agents in one root need separate worktrees.
The existing project-file, metadata and privacy bounds still apply.

Install another supported coding tool later, then rerun `forkit-radar setup`.
Use `setup --agent claude-code` or `setup --agent cursor` to select an experimental
adapter explicitly. Use installer `--no-capture` to omit automatic integration.
`setup --disable` disables callbacks first and removes only recorded Forkit hook
definitions. It restores the original config when unchanged, or preserves later
unrelated edits. History and private config backups are retained. Finish or recover
an active interval explicitly; disabling capture does not invent an end time.
`setup --status` checks configuration, not the coding tool's internal trust decision.
The private app reports the last received callback; it does not imply continuous liveness.

## Project-specific hooks (optional advanced alternative)

Run once inside your Git project:

```sh
forkit-radar hooks setup --agent codex
```

Restart Codex, trust the project and review the generated hooks with `/hooks`. Changed hooks need review again. Hooks are never enabled by bypassing Codex trust. The setup creates `.codex/hooks.json`; if a configuration already exists it refuses to replace it. Run `hooks print --agent codex` and merge the displayed entries after review. Remove those entries to uninstall capture. Recreate them if you move the Forkit installation.

Separate `--agent claude-code` and `--agent cursor` adapters use `.claude/settings.local.json` and `.cursor/hooks.json`. Both are experimental pending validation in their real applications. Cursor currently supports only local, single-workspace, non-background sessions; its start hook is fire-and-forget, so those receipts always show a partial capture.

`--registry PATH --passport-id ID` optionally associates an existing Core Passport. This remains an explicit declaration. Neither local identity nor hook-reported tool identity is proof of authorship. The installed command and private store are bound to the selected project in the generated configuration.

Codex captures the main thread lifecycle, not each assistant reply. Desktop SessionEnd may wait until the conversation is archived, the app closes, or an unopened conversation has been idle for 30 minutes. Its end hook has at most three seconds: large projects or slow disks can miss the finish. Hook failures do not prevent coding. Check `session active`, then `session recover ID` after a missed boundary; recovered intervals are partial with unknown end time. Compaction never resets an active baseline. Duplicate end events never generate extra receipts; resumed sessions create a new interval after the prior interval finishes. Start/end event ordering is assumed; hooks cannot guarantee capture if the application crashes or delivers events out of order.

Hook JSON is bounded and processed only in memory. Forkit reads the lifecycle name, session identifier, and selected workspace boundary. The external session identifier is retained only as a keyed local token while active. It never opens transcript paths or stores prompts, chats, hook payloads, credentials or model responses. Optional count reporting remains off until explicit consent.

## 2. Wrapper fallback

```sh
forkit-radar session run --tool codex -- codex
# or
forkit-radar session run --tool claude-code -- claude
```

The wrapper starts a baseline before launching the exact command you supply and creates the receipt when it exits. It needs no hooks. If project hooks are also installed, they refuse to interfere with the active wrapper. The selected coding application may require its own account or network; Forkit does not.

## 3. Manual fallback

```sh
forkit-radar start --tool cursor
# Code in your editor.
forkit-radar stop
```

All capture modes share the existing Core association, private registry, session history, JSON, diffs, evolution and local cards. No signup is inserted into that flow.

## Coverage

Capture covers supported project source files (up to 2,000), supported root dependency manifests, and declared project MCP/model/configuration metadata. Ignored files, secrets and unsupported formats are excluded. Global configuration, runtime-only tool calls, prompts, real model invocation and concurrent authorship are not inferred. A local Passport change is not automatically signed lineage. See README for full bounds.

Official references checked 2026-09-15:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Cursor hooks](https://prod.cursor.com/docs/hooks)
