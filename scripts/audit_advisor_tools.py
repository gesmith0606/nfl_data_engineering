"""Advisor Tool Audit — baseline probe for all 12 AI advisor tools.

This script probes each of the 12 advisor tools defined in
``web/frontend/src/app/api/chat/route.ts`` against the live Railway FastAPI
backend, records HTTP status + schema + domain-content validity, and writes
the results to ``.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md``.

Usage:
    # Default: probe live Railway backend
    python scripts/audit_advisor_tools.py

    # Override base URL (e.g. local dev server)
    RAILWAY_API_URL=http://localhost:8000 python scripts/audit_advisor_tools.py

    # With API key (sends X-API-Key header)
    RAILWAY_API_KEY=xxx python scripts/audit_advisor_tools.py

    # Dry-run (validate TOOL_REGISTRY without hitting the network)
    python scripts/audit_advisor_tools.py --dry-run

Exit code 0 if total FAIL == 0 else 1. WARN does NOT set a non-zero exit.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

# ---------------------------------------------------------------------------
# Constants + failure categories
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://nfldataengineering-production.up.railway.app"
DEFAULT_TIMEOUT = 15.0

# Path from the project root where the markdown report is written.
DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / ".planning"
    / "phases"
    / "63-ai-advisor-hardening"
    / "TOOL-AUDIT.md"
)

# Failure category string constants
BACKEND_DOWN = "BACKEND_DOWN"
HTTP_ERROR = "HTTP_ERROR"
EMPTY_PAYLOAD = "EMPTY_PAYLOAD"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
AUTH_BLOCKED = "AUTH_BLOCKED"
EXTERNAL_SOURCE_DOWN = "EXTERNAL_SOURCE_DOWN"
UNKNOWN = "UNKNOWN"

# Verdict strings
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

log = logging.getLogger("audit_advisor_tools")


# ---------------------------------------------------------------------------
# Probe definition
# ---------------------------------------------------------------------------
Validator = Callable[[Any], tuple[bool, str]]


@dataclass(frozen=True)
class ToolProbe:
    """A single advisor tool probe.

    Attributes:
        tool_name: Name of the advisor tool as exposed in the chat route.
        endpoint: Backend path (without base URL), e.g. ``/api/projections``.
        params: Query-string parameters for the GET request.
        validator: Function that receives the decoded JSON body and returns
            ``(ok, reason)`` where ``ok`` is True for PASS / WARN-eligible
            and False for FAIL-eligible. ``reason`` is a short machine-
            readable string recorded in the audit table.
        warn_on_empty: When True, an empty-list / empty-payload body is
            demoted from FAIL → WARN (used for off-season news / sentiment).
    """

    tool_name: str
    endpoint: str
    params: dict[str, str] = field(default_factory=dict)
    validator: Validator = field(default=lambda body: (True, "ok"))
    warn_on_empty: bool = False


# ---------------------------------------------------------------------------
# Per-tool validators
# ---------------------------------------------------------------------------
def _validate_projections_payload(body: Any) -> tuple[bool, str]:
    """Projections-shaped body: ``{projections: [{player_name, projected_points, position}]}``."""
    if not isinstance(body, dict) or "projections" not in body:
        return False, "schema:missing_projections_key"
    items = body["projections"]
    if not isinstance(items, list):
        return False, "schema:projections_not_list"
    if len(items) == 0:
        return False, "empty:no_projection_rows"
    first = items[0]
    required = {"player_name", "projected_points", "position"}
    missing = required - set(first.keys()) if isinstance(first, dict) else required
    if missing:
        return False, f"schema:missing_fields:{sorted(missing)}"
    return True, "ok"


def _validate_search_players(body: Any) -> tuple[bool, str]:
    """Search payload: list of ``{player_id, player_name}``."""
    if not isinstance(body, list):
        return False, "schema:not_list"
    if len(body) == 0:
        return False, "empty:no_search_results"
    first = body[0]
    required = {"player_id", "player_name"}
    missing = required - set(first.keys()) if isinstance(first, dict) else required
    if missing:
        return False, f"schema:missing_fields:{sorted(missing)}"
    return True, "ok"


def _validate_news_feed(body: Any) -> tuple[bool, str]:
    """News feed: list (empty is WARN-eligible via ``warn_on_empty``)."""
    if not isinstance(body, list):
        return False, "schema:not_list"
    if len(body) == 0:
        return False, "empty_payload_offseason"
    return True, "ok"


def _validate_game_predictions(body: Any) -> tuple[bool, str]:
    """Predictions: ``{predictions: [...]}`` with empty allowed in preseason."""
    if not isinstance(body, dict) or "predictions" not in body:
        return False, "schema:missing_predictions_key"
    preds = body["predictions"]
    if not isinstance(preds, list):
        return False, "schema:predictions_not_list"
    if len(preds) == 0:
        return False, "empty_payload_offseason"
    return True, "ok"


def _validate_team_roster(body: Any) -> tuple[bool, str]:
    """Lineup payload: ``{lineup: [...]}`` with len >= 1."""
    if not isinstance(body, dict) or "lineup" not in body:
        return False, "schema:missing_lineup_key"
    lineup = body["lineup"]
    if not isinstance(lineup, list):
        return False, "schema:lineup_not_list"
    if len(lineup) == 0:
        return False, "empty:no_lineup_rows"
    return True, "ok"


def _validate_team_sentiment(body: Any) -> tuple[bool, str]:
    """Team sentiment: list of ``{team, ...}``, empty allowed as WARN."""
    if not isinstance(body, list):
        return False, "schema:not_list"
    if len(body) == 0:
        return False, "no_sentiment_data"
    first = body[0]
    if not isinstance(first, dict) or "team" not in first:
        return False, "schema:missing_team_key"
    return True, "ok"


def _validate_draft_board(body: Any) -> tuple[bool, str]:
    """Draft board: ``{board: [...]}`` with len >= 50."""
    if not isinstance(body, dict) or "board" not in body:
        return False, "schema:missing_board_key"
    board = body["board"]
    if not isinstance(board, list):
        return False, "schema:board_not_list"
    if len(board) < 50:
        return False, f"empty:board_len_{len(board)}_lt_50"
    return True, "ok"


def _validate_external_rankings(body: Any) -> tuple[bool, str]:
    """External rankings: ``{players: [...]}``. Empty → FAIL EXTERNAL_SOURCE_DOWN."""
    if not isinstance(body, dict) or "players" not in body:
        return False, "schema:missing_players_key"
    players = body["players"]
    if not isinstance(players, list):
        return False, "schema:players_not_list"
    if len(players) == 0:
        return False, "external_source_unavailable"
    first = players[0]
    required = {"player_name", "external_rank", "our_rank", "rank_diff"}
    missing = required - set(first.keys()) if isinstance(first, dict) else required
    if missing:
        return False, f"schema:missing_fields:{sorted(missing)}"
    return True, "ok"


def _validate_sentiment_summary(body: Any) -> tuple[bool, str]:
    """Sentiment summary: object with ``{total_articles, bullish_players, bearish_players}``."""
    if not isinstance(body, dict):
        return False, "schema:not_object"
    required = {"total_articles", "bullish_players", "bearish_players"}
    missing = required - set(body.keys())
    if missing:
        return False, f"schema:missing_fields:{sorted(missing)}"
    return True, "ok"


# ---------------------------------------------------------------------------
# TOOL_REGISTRY — the 12 advisor tools
# ---------------------------------------------------------------------------
# Note: declared as plain assignment (no annotation) so the plan's AST-based
# verification (`ast.Assign` lookup) can detect it. Type via docstring below.
TOOL_REGISTRY = [
    ToolProbe(
        tool_name="getPlayerProjection",
        endpoint="/api/projections",
        params={"season": "2026", "week": "1", "scoring": "half_ppr"},
        validator=_validate_projections_payload,
    ),
    ToolProbe(
        tool_name="compareStartSit",
        endpoint="/api/projections",
        params={"season": "2026", "week": "1", "scoring": "half_ppr"},
        validator=_validate_projections_payload,
    ),
    ToolProbe(
        tool_name="searchPlayers",
        endpoint="/api/players/search",
        params={"q": "mahom"},
        validator=_validate_search_players,
    ),
    ToolProbe(
        tool_name="getNewsFeed",
        endpoint="/api/news/feed",
        params={"season": "2026", "limit": "10"},
        validator=_validate_news_feed,
        warn_on_empty=True,
    ),
    ToolProbe(
        tool_name="getPositionRankings",
        endpoint="/api/projections",
        params={"season": "2026", "week": "1", "position": "RB", "limit": "10"},
        validator=_validate_projections_payload,
    ),
    ToolProbe(
        tool_name="getGamePredictions",
        endpoint="/api/predictions",
        params={"season": "2026", "week": "1"},
        validator=_validate_game_predictions,
        warn_on_empty=True,
    ),
    ToolProbe(
        tool_name="getTeamRoster",
        endpoint="/api/lineups",
        params={"team": "KC", "season": "2026", "week": "1", "scoring": "half_ppr"},
        validator=_validate_team_roster,
        # Preseason / offseason has no depth chart yet — empty lineup is
        # expected and should be treated as WARN (same as news feed,
        # predictions, sentiment).
        warn_on_empty=True,
    ),
    ToolProbe(
        tool_name="getTeamSentiment",
        endpoint="/api/news/team-sentiment",
        params={"season": "2026", "week": "1"},
        validator=_validate_team_sentiment,
        warn_on_empty=True,
    ),
    ToolProbe(
        tool_name="getPlayerNews",
        endpoint="/api/news/feed",
        params={"season": "2026", "limit": "25"},
        validator=_validate_news_feed,
        warn_on_empty=True,
    ),
    ToolProbe(
        tool_name="getDraftBoard",
        endpoint="/api/draft/board",
        params={"scoring": "half_ppr"},
        validator=_validate_draft_board,
    ),
    ToolProbe(
        tool_name="compareExternalRankings",
        endpoint="/api/rankings/compare",
        params={"source": "sleeper", "scoring": "half_ppr", "limit": "20"},
        validator=_validate_external_rankings,
    ),
    ToolProbe(
        tool_name="getSentimentSummary",
        endpoint="/api/news/summary",
        params={"season": "2026", "week": "1"},
        validator=_validate_sentiment_summary,
    ),
]


# ---------------------------------------------------------------------------
# Probe + categorization
# ---------------------------------------------------------------------------
def _classify_failure(
    *,
    error: Exception | None,
    status_code: int | None,
    validator_reason: str,
    validator_ok: bool,
) -> str:
    """Map a probe outcome to one of the failure category constants."""
    if isinstance(error, (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)):
        return BACKEND_DOWN
    if error is not None:
        return UNKNOWN
    if status_code == 401:
        return AUTH_BLOCKED
    if status_code == 404:
        return HTTP_ERROR
    if status_code is not None and status_code >= 500:
        return HTTP_ERROR
    if status_code is not None and status_code >= 400:
        return HTTP_ERROR
    if not validator_ok:
        if "external_source" in validator_reason:
            return EXTERNAL_SOURCE_DOWN
        if validator_reason.startswith("schema:"):
            return SCHEMA_MISMATCH
        if validator_reason.startswith("empty") or validator_reason in {
            "empty_payload_offseason",
            "no_sentiment_data",
        }:
            return EMPTY_PAYLOAD
        return UNKNOWN
    return ""  # empty == no failure


def probe(client: httpx.Client, tool_probe: ToolProbe) -> dict[str, Any]:
    """Probe a single advisor tool and return a result dict.

    Args:
        client: Shared ``httpx.Client`` instance (with timeout + headers).
        tool_probe: The tool probe descriptor.

    Returns:
        A dict with keys: ``tool_name``, ``endpoint``, ``params``, ``status_code``,
        ``latency_ms``, ``ok``, ``verdict`` (PASS/WARN/FAIL), ``category``,
        ``reason``, ``body_keys``, ``sample``, ``error``.
    """
    started = time.perf_counter()
    status_code: int | None = None
    error: Exception | None = None
    body: Any = None
    sample = ""
    body_keys = ""

    try:
        response = client.get(tool_probe.endpoint, params=tool_probe.params)
        status_code = response.status_code
        raw_text = response.text or ""
        sample = raw_text[:200]
        if status_code < 400:
            try:
                body = response.json()
            except ValueError as json_err:
                error = json_err
    except httpx.HTTPError as exc:
        error = exc
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)

    # Describe body shape for the table
    if isinstance(body, dict):
        body_keys = "{" + ",".join(sorted(body.keys())) + "}"
    elif isinstance(body, list):
        body_keys = f"list[{len(body)}]"
    elif body is None:
        body_keys = "<none>"
    else:
        body_keys = type(body).__name__

    # Run validator only when we have a decoded body and no transport error
    validator_ok = False
    validator_reason = ""
    if (
        error is None
        and status_code is not None
        and status_code < 400
        and body is not None
    ):
        try:
            validator_ok, validator_reason = tool_probe.validator(body)
        except Exception as val_err:  # pragma: no cover - defensive
            validator_ok = False
            validator_reason = f"validator_exception:{val_err!r}"
    elif error is not None:
        validator_reason = f"transport_error:{type(error).__name__}"
    elif status_code is not None and status_code >= 400:
        validator_reason = f"http_status_{status_code}"
    else:
        validator_reason = "no_body_to_validate"

    category = _classify_failure(
        error=error,
        status_code=status_code,
        validator_reason=validator_reason,
        validator_ok=validator_ok,
    )

    # Determine verdict (PASS / WARN / FAIL)
    if category == "":
        verdict = PASS
        reason = "ok"
    else:
        is_empty_like = category in {EMPTY_PAYLOAD}
        if is_empty_like and tool_probe.warn_on_empty:
            verdict = WARN
        else:
            verdict = FAIL
        reason = validator_reason or category

    return {
        "tool_name": tool_probe.tool_name,
        "endpoint": tool_probe.endpoint,
        "params": tool_probe.params,
        "status_code": status_code if status_code is not None else "-",
        "latency_ms": latency_ms,
        "ok": verdict == PASS,
        "verdict": verdict,
        "category": category or "-",
        "reason": reason,
        "body_keys": body_keys,
        "sample": sample,
        "error": repr(error) if error is not None else None,
    }


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------
def _cell(s: str, max_len: int = 80) -> str:
    """Sanitize a string for embedding inside a markdown table cell."""
    if s is None:
        return ""
    s = str(s).replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def write_audit_markdown(
    results: list[dict[str, Any]],
    out_path: Path,
    *,
    base_url: str,
    auth_header_present: bool,
) -> None:
    """Write the TOOL-AUDIT.md baseline table to ``out_path``.

    Args:
        results: Output of ``probe()`` per tool — one dict per row.
        out_path: Destination path for the markdown file.
        base_url: The Railway base URL used for the probe.
        auth_header_present: True when ``X-API-Key`` was attached.
    """
    pass_count = sum(1 for r in results if r["verdict"] == PASS)
    warn_count = sum(1 for r in results if r["verdict"] == WARN)
    fail_count = sum(1 for r in results if r["verdict"] == FAIL)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    lines.append("# Advisor Tool Audit — Baseline\n")
    lines.append(
        "Baseline measurement of the 12 AI advisor tools defined in "
        "`web/frontend/src/app/api/chat/route.ts`. Wave-2 plans (63-02, 63-03, 63-04) "
        "will target the failure categories identified below.\n"
    )
    lines.append("## Run Metadata\n")
    lines.append(f"- **Run (UTC):** {run_ts}")
    lines.append(f"- **Base URL:** `{base_url}`")
    lines.append(
        f"- **Auth header (X-API-Key):** {'present' if auth_header_present else 'absent'}"
    )
    lines.append(f"- **Probes executed:** {len(results)}")
    lines.append(
        f"- **Totals:** {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL"
    )
    lines.append("")
    lines.append("## Tool Status Table\n")
    lines.append(
        "| Tool | Endpoint | HTTP | Latency (ms) | Status | Category | Reason | Sample |"
    )
    lines.append(
        "|------|----------|------|--------------|--------|----------|--------|--------|"
    )
    for r in results:
        lines.append(
            "| {tool} | {endpoint} | {http} | {latency} | {status} | {cat} | {reason} | {sample} |".format(
                tool=_cell(r["tool_name"], 40),
                endpoint=_cell(r["endpoint"], 40),
                http=_cell(str(r["status_code"]), 6),
                latency=_cell(str(r["latency_ms"]), 8),
                status=_cell(r["verdict"], 6),
                cat=_cell(r["category"], 24),
                reason=_cell(r["reason"], 50),
                sample=_cell(r["sample"], 60),
            )
        )

    lines.append("")
    lines.append("## Failure Detail\n")
    fails = [r for r in results if r["verdict"] == FAIL]
    if not fails:
        lines.append("_No failures — all tools PASS or WARN._\n")
    else:
        for r in fails:
            lines.append(f"### {r['tool_name']} — {r['category']}")
            lines.append(f"- **Endpoint:** `{r['endpoint']}`")
            lines.append(f"- **Params:** `{r['params']}`")
            lines.append(
                f"- **HTTP:** {r['status_code']} (latency {r['latency_ms']}ms)"
            )
            lines.append(f"- **Body shape:** `{r['body_keys']}`")
            lines.append(f"- **Reason:** `{r['reason']}`")
            if r["error"]:
                lines.append(f"- **Error:** `{r['error']}`")
            snippet = (r["sample"] or "")[:500]
            if snippet:
                lines.append("- **Body sample (500 chars):**")
                lines.append("")
                lines.append("```json")
                lines.append(snippet)
                lines.append("```")
            lines.append("")

    lines.append("## Warning Detail\n")
    warns = [r for r in results if r["verdict"] == WARN]
    if not warns:
        lines.append("_No warnings._\n")
    else:
        for r in warns:
            lines.append(f"- **{r['tool_name']}** → {r['category']} / `{r['reason']}`")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _build_client(base_url: str, api_key: str) -> httpx.Client:
    """Construct a shared httpx.Client with timeout + optional auth header."""
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    return httpx.Client(
        base_url=base_url,
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )


def run_audit(base_url: str, api_key: str) -> list[dict[str, Any]]:
    """Probe every tool in ``TOOL_REGISTRY`` and return the list of results."""
    results: list[dict[str, Any]] = []
    with _build_client(base_url, api_key) as client:
        for tp in TOOL_REGISTRY:
            log.info("Probing %s → %s", tp.tool_name, tp.endpoint)
            result = probe(client, tp)
            results.append(result)
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns process exit code."""
    parser = argparse.ArgumentParser(
        description="Probe all 12 advisor tools against the live Railway backend."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate TOOL_REGISTRY without hitting the network.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write TOOL-AUDIT.md (default: phase directory).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    base_url = os.environ.get("RAILWAY_API_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("RAILWAY_API_KEY", "")

    if args.dry_run:
        # Sanity-check TOOL_REGISTRY without network I/O.
        print(f"DRY-RUN: {len(TOOL_REGISTRY)} probes defined")
        for tp in TOOL_REGISTRY:
            print(f"  - {tp.tool_name} → GET {tp.endpoint} params={tp.params}")
        if len(TOOL_REGISTRY) != 12:
            print(f"ERROR: expected 12 probes, got {len(TOOL_REGISTRY)}")
            return 1
        return 0

    log.info("Base URL: %s", base_url)
    log.info("Auth header: %s", "present" if api_key else "absent")

    results = run_audit(base_url, api_key)

    pass_count = sum(1 for r in results if r["verdict"] == PASS)
    warn_count = sum(1 for r in results if r["verdict"] == WARN)
    fail_count = sum(1 for r in results if r["verdict"] == FAIL)

    write_audit_markdown(
        results,
        args.output,
        base_url=base_url,
        auth_header_present=bool(api_key),
    )

    summary = f"AUDIT: {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL"
    print(summary)
    log.info("Wrote %s", args.output)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
