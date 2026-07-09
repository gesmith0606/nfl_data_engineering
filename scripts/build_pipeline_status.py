"""Build the pipeline-status snapshot for the ops dashboard.

Fetches recent GitHub Actions run history for every scheduled workflow and
writes ``data/ops/pipeline_status.json``. Runs inside the 6-hourly
freshness-monitor workflow (where ``GITHUB_TOKEN`` exists), and the file is
committed so the HF Spaces backend can serve it — the Space itself has no
GitHub credentials, which is why this is a build-and-commit pattern rather
than a live API proxy.

Usage:
    GITHUB_TOKEN=... python scripts/build_pipeline_status.py
    python scripts/build_pipeline_status.py --repo owner/name --output path.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "ops" / "pipeline_status.json"
DEFAULT_REPO = "gesmith0606/nfl_data_engineering"

# The scheduled workflows shown on the dashboard, with human-readable
# schedule descriptions (kept in sync with each yml's cron block by hand —
# they change rarely and the description is display copy, not logic).
WORKFLOWS: List[Dict[str, str]] = [
    {
        "file": "weekly-pipeline.yml",
        "name": "Weekly Pipeline",
        "schedule": "Tuesdays 09:00 UTC",
        "purpose": "Bronze → Silver → Gold projections (--ml hybrids)",
    },
    {
        "file": "daily-sentiment.yml",
        "name": "Daily Sentiment",
        "schedule": "Daily 12:00 UTC",
        "purpose": "News ingestion + rankings refresh + archive",
    },
    {
        "file": "odds-capture.yml",
        "name": "Odds Capture",
        "schedule": "Daily 13:00 & 21:00 UTC · props Sun/Thu",
        "purpose": "Spread snapshots + player props",
    },
    {
        "file": "sunday-refresh.yml",
        "name": "Sunday Refresh",
        "schedule": "Sundays 15:35 & 16:45 UTC (in-season)",
        "purpose": "Post-inactives projection refresh",
    },
    {
        "file": "weekly-external-projections.yml",
        "name": "External Projections",
        "schedule": "Tue 14:00 & Sun 12:00 UTC",
        "purpose": "Sleeper/FantasyPros ingestion + grading",
    },
    {
        "file": "freshness-monitor.yml",
        "name": "Freshness Monitor",
        "schedule": "Every 6 hours",
        "purpose": "Data staleness probe (builds this dashboard)",
    },
    {
        "file": "deploy-web.yml",
        "name": "Deploy Web",
        "schedule": "On push to main",
        "purpose": "Sanity gates + HF/Vercel deploy verification",
    },
]


def fetch_workflow_runs(
    repo: str, workflow_file: str, token: str, per_page: int = 10
) -> List[Dict[str, Any]]:
    """Fetch the most recent runs for one workflow via the GitHub REST API.

    Args:
        repo:          ``owner/name`` repository slug.
        workflow_file: Workflow filename (e.g. ``weekly-pipeline.yml``).
        token:         GitHub token (the Actions-provided ``GITHUB_TOKEN``
                       is sufficient — read access to the same repo).
        per_page:      Number of recent runs to fetch (dashboard uses the
                       default 10 everywhere; the knob exists for ad-hoc use).

    Returns:
        List of raw run dicts (may be empty).

    Raises:
        requests.HTTPError: On non-2xx responses (caller fails open).
    """
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/"
        f"{workflow_file}/runs"
    )
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        params={"per_page": per_page},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("workflow_runs", [])


def _duration_seconds(run: Dict[str, Any]) -> Optional[int]:
    """Approximate wall-clock duration of a run, or None while in progress.

    Uses ``updated_at`` as the end timestamp — the /runs list endpoint has
    no true completion field (that lives on per-job records). For runs that
    queued a while before a runner picked them up, this overstates duration
    by the queue time. Good enough for a dashboard; not billing-grade.
    """
    started = run.get("run_started_at")
    updated = run.get("updated_at")
    if not started or not updated or run.get("status") != "completed":
        return None
    try:
        t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        return max(0, int((t1 - t0).total_seconds()))
    except ValueError:
        return None


def summarize_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reduce raw run dicts to the dashboard payload for one workflow.

    Args:
        runs: Raw workflow-run dicts, newest first (GitHub API order).

    Returns:
        Dict with ``last_run`` (or None), ``recent`` conclusion strings
        (newest first) and ``success_rate`` over completed recent runs.
    """
    if not runs:
        return {"last_run": None, "recent": [], "success_rate": None}

    latest = runs[0]
    last_run = {
        "status": latest.get("status"),
        "conclusion": latest.get("conclusion"),
        "started_at": latest.get("run_started_at"),
        "duration_seconds": _duration_seconds(latest),
        "html_url": latest.get("html_url"),
        "event": latest.get("event"),
    }
    recent = [r.get("conclusion") or r.get("status") or "unknown" for r in runs]
    completed = [r for r in runs if r.get("status") == "completed"]
    success_rate = (
        round(
            sum(1 for r in completed if r.get("conclusion") == "success")
            / len(completed),
            3,
        )
        if completed
        else None
    )
    return {"last_run": last_run, "recent": recent, "success_rate": success_rate}


def build_status(repo: str, token: str) -> Dict[str, Any]:
    """Assemble the full pipeline-status document.

    Fails open per workflow: an API error on one workflow records an
    ``error`` field for it and continues, so a single flaky call never
    blanks the whole dashboard.
    """
    workflows_out = []
    for wf in WORKFLOWS:
        entry: Dict[str, Any] = dict(wf)
        try:
            runs = fetch_workflow_runs(repo, wf["file"], token)
            entry.update(summarize_runs(runs))
        except Exception as exc:  # noqa: BLE001 — fail-open per workflow
            logger.warning("Could not fetch runs for %s: %s", wf["file"], exc)
            entry.update(
                {
                    "last_run": None,
                    "recent": [],
                    "success_rate": None,
                    "error": str(exc),
                }
            )
        workflows_out.append(entry)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "workflows": workflows_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        logger.error("GITHUB_TOKEN not set — cannot query the Actions API")
        return 1

    status = build_status(args.repo, token)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2))
    ok = sum(1 for w in status["workflows"] if w.get("last_run"))
    logger.info(
        "Wrote %s (%d/%d workflows with run history)",
        out,
        ok,
        len(status["workflows"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
