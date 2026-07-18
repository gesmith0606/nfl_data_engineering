---
name: data-pipeline-alerting
description: >-
  Monitoring and alerting for DATA PIPELINES — deciding what to watch (job failure, freshness/
  staleness, row-volume anomalies, schema drift, SLA breach, and the dead-man's-switch for a job that
  never ran), then routing ACTIONABLE alerts to Slack and email without causing alert fatigue
  (severity tiers, dedup, thresholds, runbooks). Use when wiring alerts/monitoring into a pipeline,
  defining data SLAs, getting notified when data is late/missing/wrong/anomalous, or fixing a noisy
  alerting setup. Pairs with `data-quality` (the assertions it alerts on) and `cheap-data-orchestration`
  (the scheduler it runs in). Do NOT use for in-code error-handling/retry patterns (use `error-handling`),
  for ML model/serving monitoring (use `mle-workflow`), or for reviewing code for swallowed errors
  (use the `silent-failure-hunter` agent).
---

# data-pipeline-alerting

A green pipeline can still ship **stale, empty, or wrong** data. This skill is about catching that and
telling the right person — once, actionably — instead of drowning them in noise.

Examples target a **Snowflake + dbt + GitHub Actions** cron stack routing to **Slack + email**, but the
principles are tool-agnostic. Keep credentials in env/secret manager (see `secrets-handling`).

## When to use vs neighbors
- **This skill** — what to monitor + alert design + routing (Slack/email).
- `data-quality` — the assertions themselves (uniqueness/freshness/range); this **alerts on their results**.
- `cheap-data-orchestration` — the scheduler the checks run inside.
- `error-handling` — in-code retries/circuit-breakers (the job's own resilience), not notifications.
- `silent-failure-hunter` (agent) — finds swallowed errors in *code*, not in *data*.

## Monitor the data, not just the job
The core mistake is alerting only on exit code. Watch these signals (catalog + SQL → references):
- **Job failure** — the run threw / exited non-zero.
- **Freshness / staleness** — newest row older than the SLA (dbt source freshness, or `max(loaded_at)`).
- **Volume anomaly** — row count vs expected (±% band or vs trailing median); **0 rows** is the classic.
- **Schema drift** — columns added/removed/retyped upstream.
- **Quality-gate failure** — a `data-quality` assertion failed (tie-out, null spike, out-of-range).
- **Dead-man's-switch** — the job **didn't run at all** (cron skipped, runner down). The alert nobody
  builds and everybody needs — *silence is not success*.
- **Runtime / cost spike** — a run far slower or burning more credits than baseline.

## Alert design: actionable, once, to an owner
Noise kills alerting. Rules:
- **Severity tiers.** *critical* (data down / SLA breached / wrong numbers shipped) → Slack now (+ page
  if you add one); *warning* (degraded but recoverable) → Slack low-pri or email; *info* → digest only.
- **Every alert is actionable** — name what broke, where, the impact, and link to the run + a **runbook**.
  No action ⇒ it's a dashboard metric, not an alert.
- **Dedup & group** — one alert per incident, not per failed row; suppress repeats while firing; group
  related failures into one message.
- **Thresholds with hysteresis** — bands + "N consecutive" to stop flapping; send a clear/recovered note.
- **Ownership & routing** — each pipeline has an owner + channel; route there, not a firehose.
- **Snooze/mute** — let humans silence a known-broken upstream without ripping out the wiring.

## Routing: Slack + email
- **Slack incoming webhook** for real-time (critical + warning): a structured message — severity emoji,
  pipeline, signal, impact, run link, runbook link.
- **Email (SMTP / SES)** for digests + lower-urgency SLA notices: a daily/weekly "pipeline health"
  summary, plus individual emails for warnings that don't warrant a ping.
- **Severity → channel map:** critical → Slack `#data-alerts` (+ email); warning → Slack or email; info
  → daily email digest only.

Concrete senders (Slack webhook + SES/SMTP) + message format → `references/routing-slack-email.md`.

## Wire it into the stack
- Run checks as a **GitHub Actions** step after the pipeline (`cheap-data-orchestration` cron): dbt
  source freshness + `dbt test`, plus custom SQL monitors on Snowflake; parse dbt's `run_results.json`.
- On a tripped check, call the Slack/email sender with the structured payload. A check that *itself*
  errors must also alert — don't let the monitor fail silently.
- **Dead-man's-switch:** a heartbeat (ping healthchecks.io on success, or a scheduled "was there a run
  in the last N hours?" query) so a job that never started still alerts.
- Keep alert config (thresholds, owners, channels) in version control next to the pipeline.

## References
- `references/signals-and-checks.md` — monitor catalog: Snowflake SQL + dbt freshness/volume/drift/dead-man.
- `references/routing-slack-email.md` — Slack webhook + email (SES/SMTP) sender code, severity routing, format.
