"""Record a Claude Haiku response fixture for VCR replay (Plan 72-02).

Re-records the W17 / W18 batched-extraction fixtures used by the
deterministic test suite (LLM-03 benchmark + LLM-04 cost projection +
``test_pipeline_claude_primary`` + ``test_batched_claude_extractor``).

The recording is faithful to whatever Claude returns: this script writes
``response_text`` verbatim from the live API response. It does **not**
post-process subject_type, synthesise event flags, or edit individual
items. If the response fails the verification gates documented in
``tests/fixtures/claude_responses/README.md``, the operator strengthens
the prompt in ``src/sentiment/processing/extractor.py::_SYSTEM_PREFIX``
and re-records — never patches the JSON.

Usage
-----
::

    source venv/bin/activate
    export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2)
    python scripts/record_claude_fixture.py --week 17 \\
        --out tests/fixtures/claude_responses/offseason_batch_w17.json

    # Then immediately (within ~5 min so cache stays warm):
    python scripts/record_claude_fixture.py --week 18 \\
        --out tests/fixtures/claude_responses/offseason_batch_w18.json

Determinism contract (Plan 71-02 + Plan 72-02)
----------------------------------------------
The fixture is recorded with ``roster_provider=lambda: []`` so the
``prompt_sha`` depends only on ``_SYSTEM_PREFIX`` + the per-doc user
block. Any non-empty roster would drift the SHA across machines and
break ``FakeClaudeClient`` strict-mode replay.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Anchor on repo root so ``import src.*`` works when the script is
# invoked from any cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from src.sentiment.processing.extractor import (  # noqa: E402
    _CLAUDE_MODEL,
    _MAX_TOKENS_BATCH,
    _SYSTEM_PREFIX,
    _build_batched_prompt_for_sha,
)
from tests.sentiment.fakes import prompt_sha  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("record_claude_fixture")

_BRONZE_FIXTURE = Path(
    "tests/fixtures/bronze_sentiment/offseason_w17_w18.json"
)


def _load_week_docs(week: int) -> List[Dict[str, Any]]:
    """Load the W17 or W18 batch (15 docs) from the Bronze fixture.

    Args:
        week: Either 17 or 18.

    Returns:
        15-doc list, in the order they appear in the fixture file.
    """
    payload = json.loads((_REPO_ROOT / _BRONZE_FIXTURE).read_text())
    items = payload.get("items", [])
    docs = [d for d in items if int(d.get("week", -1)) == week]
    if len(docs) != 15:
        raise ValueError(
            f"Expected 15 docs for week={week}; got {len(docs)} in "
            f"{_BRONZE_FIXTURE}"
        )
    return docs


def _record_one_call(
    docs: List[Dict[str, Any]],
) -> Tuple[str, Dict[str, int], str]:
    """Build the prompt, call Claude, return ``(response_text, usage, sha)``.

    Args:
        docs: 15 Bronze docs for the chosen week.

    Returns:
        Tuple ``(response_text, usage_dict, prompt_sha)``.

    Raises:
        KeyError: if ``ANTHROPIC_API_KEY`` is not set in the environment.
        Exception: any error from ``anthropic.Anthropic.messages.create``.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise KeyError(
            "ANTHROPIC_API_KEY not set in environment. Live API call "
            "needed to record fixtures. Source from .env via:\n"
            "  export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | "
            "cut -d= -f2)"
        )

    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=api_key)

    # roster_provider=lambda: [] — Plan 71-02 / 72-02 determinism contract.
    system, messages = _build_batched_prompt_for_sha(
        static_prefix=_SYSTEM_PREFIX,
        roster_block="",
        batch_docs=docs,
    )
    sha = prompt_sha(system, messages, _CLAUDE_MODEL)

    logger.info("Calling Claude (model=%s, batch=%d)", _CLAUDE_MODEL, len(docs))
    response = client.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=_MAX_TOKENS_BATCH,
        system=system,
        messages=messages,
    )

    # Faithful recording: store response.content[0].text verbatim.
    response_text = response.content[0].text
    usage = {
        "input_tokens": int(getattr(response.usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(response.usage, "output_tokens", 0) or 0),
        "cache_read_input_tokens": int(
            getattr(response.usage, "cache_read_input_tokens", 0) or 0
        ),
        "cache_creation_input_tokens": int(
            getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        ),
    }
    logger.info(
        "Recorded: sha=%s usage=%s", sha[:16] + "...", usage
    )
    return response_text, usage, sha


def _verify_fixture(spec: Dict[str, Any], week: int) -> None:
    """Apply Plan 72-02 hard gates to a freshly recorded fixture.

    Hard gates:
      * ``prompt_sha`` is a 64-char hex string.
      * Cache discipline matches the week role
        (W17 cold-cache: ``cache_creation > 0``, ``cache_read == 0``;
         W18 warm-cache: ``cache_read > 0``, ``cache_creation == 0``).
      * ``response_text`` parses as a JSON array.
      * Every item has a non-empty ``subject_type`` field.
      * At least one item each of ``coach``/``team``/``reporter`` values.
      * At least 5 items have one of the 7 new draft-season flags set
        in their ``events`` sub-dict.

    Args:
        spec: The about-to-be-written fixture dict.
        week: 17 (cold cache) or 18 (warm cache).

    Raises:
        AssertionError: with diagnostic if any hard gate fails. The
            operator's response is to strengthen the prompt and re-record,
            never patch the file.
    """
    sha = spec.get("prompt_sha", "")
    assert len(sha) == 64, f"prompt_sha must be 64 hex chars; got {len(sha)}"

    cache_read = int(spec.get("cache_read_input_tokens", 0))
    cache_creation = int(spec.get("cache_creation_input_tokens", 0))
    if week == 17:
        assert cache_creation > 0, (
            f"W17 must be cold-cache (cache_creation > 0); got {cache_creation}"
        )
        assert cache_read == 0, (
            f"W17 must be cold-cache (cache_read == 0); got {cache_read}"
        )
    elif week == 18:
        assert cache_read > 0, (
            f"W18 must be warm-cache (cache_read > 0); got {cache_read}"
        )
        assert cache_creation == 0, (
            f"W18 must be warm-cache (cache_creation == 0); got {cache_creation}"
        )

    items = json.loads(spec["response_text"])
    assert isinstance(items, list), "response_text must decode to a JSON array"

    missing_st = [i for i in items if isinstance(i, dict) and not i.get("subject_type")]
    assert not missing_st, (
        f"Every item must carry a subject_type per the strengthened prompt. "
        f"{len(missing_st)} item(s) missing subject_type — strengthen the "
        f"prompt and re-record (do NOT patch this file)."
    )

    subject_types = {
        i.get("subject_type") for i in items if isinstance(i, dict)
    }
    assert {"coach", "team", "reporter"}.issubset(subject_types), (
        f"Need at least one each of subject_type ∈ "
        f"{{coach, team, reporter}}; got {subject_types}"
    )

    new_flags = (
        "is_drafted",
        "is_rumored_destination",
        "is_coaching_change",
        "is_trade_buzz",
        "is_holdout",
        "is_cap_cut",
        "is_rookie_buzz",
    )
    new_flag_count = sum(
        1
        for i in items
        if isinstance(i, dict)
        and any((i.get("events") or {}).get(f) for f in new_flags)
    )
    assert new_flag_count >= 5, (
        f"Need >= 5 items carrying one of the 7 new flags; got {new_flag_count}"
    )

    logger.info(
        "Verification OK: items=%d subject_types=%s new_flag_items=%d",
        len(items),
        subject_types,
        new_flag_count,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--week",
        type=int,
        required=True,
        choices=[17, 18],
        help="Week to record (17=cold cache, 18=warm cache)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output fixture path (overwrites if exists).",
    )
    args = parser.parse_args()

    docs = _load_week_docs(args.week)
    response_text, usage, sha = _record_one_call(docs)

    spec = {
        "_comment": (
            f"Recorded Claude Haiku 4.5 response for 2025 W{args.week} "
            f"offseason batch (Plan 72-02 re-record against post-72-01 "
            f"prompt + REQUIRED subject_type strengthening). prompt_sha "
            f"computed via _build_batched_prompt_for_sha with "
            f"roster_provider=lambda: []. Each item must include a "
            f"subject_type field per the strengthened prompt; recordings "
            f"are faithful (no Python post-processing)."
        ),
        "prompt_sha": sha,
        "model": _CLAUDE_MODEL,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_input_tokens": usage["cache_read_input_tokens"],
        "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
        "response_text": response_text,
    }

    _verify_fixture(spec, args.week)

    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec, indent=2))
    logger.info("Wrote fixture: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
