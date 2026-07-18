# Routing: Slack webhook + email (SES/SMTP)

Concrete senders + a severity router. Run with `python3`. **Never hardcode webhook URLs or SMTP
credentials** — resolve from env / a secret manager (see the `secrets-handling` skill).

## A structured alert payload
Keep one dataclass so every signal produces a consistent, actionable message:
```python
from dataclasses import dataclass

@dataclass
class Alert:
    severity: str      # "critical" | "warning" | "info" | "recovered"
    pipeline: str      # e.g. "orders_daily"
    signal: str        # e.g. "freshness", "volume", "dead-man"
    summary: str       # one line: what broke
    impact: str        # who/what is affected
    run_url: str = ""  # link to the GitHub Actions run
    runbook_url: str = ""

EMOJI = {"critical": "🔴", "warning": "🟠", "info": "🔵", "recovered": "🟢"}
```

## Slack (incoming webhook)
```python
import os, json, urllib.request

def send_slack(a: Alert) -> None:
    url = os.environ["SLACK_WEBHOOK_URL"]            # set as a GH Actions secret
    text = (f"{EMOJI[a.severity]} *{a.severity.upper()}* — `{a.pipeline}` / {a.signal}\n"
            f"{a.summary}\n*Impact:* {a.impact}")
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    links = " | ".join(x for x in [
        f"<{a.run_url}|run>" if a.run_url else "",
        f"<{a.runbook_url}|runbook>" if a.runbook_url else ""] if x)
    if links:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": links}]})
    body = json.dumps({"text": a.summary, "blocks": blocks}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)
```

## Email — SES (boto3) or plain SMTP
```python
import os, boto3   # SES path
def send_email_ses(a: Alert, to_addrs: list[str]) -> None:
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    subject = f"[{a.severity.upper()}] {a.pipeline}: {a.signal}"
    body = (f"{a.summary}\n\nImpact: {a.impact}\nRun: {a.run_url}\nRunbook: {a.runbook_url}")
    ses.send_email(Source=os.environ["ALERT_FROM"],
                   Destination={"ToAddresses": to_addrs},
                   Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}})
```
```python
import os, smtplib                       # SMTP path (if not on SES)
from email.message import EmailMessage
def send_email_smtp(a: Alert, to_addrs: list[str]) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[{a.severity.upper()}] {a.pipeline}: {a.signal}"
    msg["From"] = os.environ["ALERT_FROM"]; msg["To"] = ", ".join(to_addrs)
    msg.set_content(f"{a.summary}\n\nImpact: {a.impact}\nRun: {a.run_url}\nRunbook: {a.runbook_url}")
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))) as s:
        s.starttls(); s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"]); s.send_message(msg)
```

## Severity router (one entry point)
```python
def route(a: Alert) -> None:
    if a.severity in ("critical", "recovered"):
        send_slack(a)                       # real-time
        if a.severity == "critical":
            send_email_ses(a, ["data-oncall@example.com"])   # + paging trail
    elif a.severity == "warning":
        send_slack(a)                       # low-pri channel, or swap to email
    # info -> collected into the daily digest, not sent in real-time
```

## Daily digest (info / summary)
Accumulate non-critical events during the day (a table or a JSON artifact) and email one summary on a
separate scheduled run — far better than 50 individual "info" emails:
```python
def send_digest(rows: list[Alert]) -> None:
    if not rows: return
    body = "\n".join(f"- [{r.severity}] {r.pipeline}/{r.signal}: {r.summary}" for r in rows)
    send_email_ses(Alert("info", "pipeline-health", "digest",
                         f"{len(rows)} events in the last 24h", "all pipelines"),
                   ["data-team@example.com"])  # attach `body` in a real impl
```

## GitHub Actions wiring (sketch)
```yaml
- name: run monitors
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
    SNOWFLAKE_PASSWORD: ${{ secrets.SNOWFLAKE_PASSWORD }}
    ALERT_FROM: alerts@example.com
  run: python3 monitors/run_checks.py     # runs checks, calls route() on trips
```
Secrets come from GitHub Actions secrets (or OIDC → cloud), never the repo — see `secrets-handling`.
A check script that raises should `route()` a critical "monitor failed" alert in its own except block.
