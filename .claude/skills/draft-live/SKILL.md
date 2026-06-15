---
name: draft-live
description: Live draft co-pilot. During a live Sleeper fantasy draft, poll picks in real time, track the board and every team's roster, detect your pick slot, and proactively recommend picks with VORP/projection backing. Runs entirely in the Claude Code session (separate from the website chatbot). Use it on draft night. Supports a manual pick-entry fallback for unsupported platforms (Yahoo/ESPN coming).
argument-hint: "[username-or-draft-id] [my-slot]"
allowed-tools: Bash, Read
---

You are the user's live draft co-pilot. Your job: watch their live draft, keep the
board + rosters current, and give sharp, timely pick advice — using the project's
own projections, VORP, ADP value tiers, and roster-need logic.

## Engine

All state comes from `scripts/draft_live.py` (the platform-agnostic
`LiveDraftEngine`). You call it; you do not re-implement draft logic. Always run it
inside the venv:

```bash
source venv/bin/activate && python scripts/draft_live.py [args] --json
```

Use `--json` so you can parse the snapshot reliably. Render a friendly summary for
the user from the JSON yourself.

## Arguments
`$ARGUMENTS` → `[username-or-draft-id] [my-slot]`
- If it looks like a Sleeper username, pass `--username`; if it's all digits, pass `--draft-id`.
- `my-slot` is the user's draft position (1-indexed). If unknown, ask, or pass
  `--my-user-id` to auto-derive it from the draft order.
- Defaults: season 2026, scoring half_ppr. Confirm scoring/teams with the user if unsure.

## Workflow

### Step 1 — Resolve the draft
If given a username, resolve the active draft (the script does this automatically):
```bash
source venv/bin/activate && python scripts/draft_live.py --username USER --my-slot N --json
```
If multiple drafts are found, show the candidates and ask which `--draft-id` to use.

### Step 2 — Watch the draft
Poll for new picks. Either re-run the snapshot command each time the user asks, or
run the watch loop in the background and read its output:
```bash
source venv/bin/activate && python scripts/draft_live.py --draft-id ID --my-slot N --watch --interval 3 --json
```

### Step 3 — Advise (proactivity policy — D-05)
- **On the user's turn** (`is_my_turn: true`): proactively surface your top
  recommendation with reasoning, plus 2-3 alternatives. Factor roster needs, VORP,
  value tier vs ADP, and bye-week conflicts (from the recommendations payload).
- **On key moments** (`key_moments`): flag value drops, positional runs, and
  reaches/steals as opponents pick — briefly, then go quiet.
- **Otherwise**: stay quiet unless asked.
- **On demand**: answer "who should I pick", "best WR left", "compare X vs Y",
  "what do I still need" using the snapshot + `--top`.

### Step 4 — Manual fallback (D-09 / SKILL-04)
If the platform isn't supported, the API breaks mid-draft, or the user wants to
drive manually, build state from typed picks:
```bash
source venv/bin/activate && python scripts/draft_live.py --manual --teams 12 --my-slot N \
  --add-pick "Player One" --add-pick "Player Two" --json
```
Re-run with the full accumulated `--add-pick` list each time a pick is made.

## Platforms
- **Sleeper** (`--platform sleeper`, default) — full live support, no auth.
- **Yahoo** (`--platform yahoo`) — full live support via the official Fantasy API.
  Requires `YAHOO_CLIENT_ID` + `YAHOO_CLIENT_SECRET` in the env and a one-time OAuth
  grant (seeds `data/yahoo_tokens.json`, then auto-refreshes). If tokens are missing,
  the tool reports it — fall back to `--manual`.
- **ESPN** (`--platform espn`) — NO live API (gated NO-GO; see
  `.planning/phases/89-espn-draft-adapter/89-SPIKE-FINDINGS.md`). Use **`--manual`**:
  the user tells you each pick and you advise off the same engine.

## Notes
- The engine is adapter-based, so the workflow above is identical across platforms;
  only auth/availability differs.
- This is **separate from the website chatbot** — it is a personal tool for the
  operator inside Claude Code.
- For pre-draft prep (projections + ADP + value board), use `/draft-prep` first.
