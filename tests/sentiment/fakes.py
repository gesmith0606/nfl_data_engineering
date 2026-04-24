"""Deterministic test doubles for the Anthropic Claude client (Plan 71-02).

This module ships ``FakeClaudeClient``: a replay-only double that duck-types
``anthropic.Anthropic`` via a ``.messages.create(...)`` surface. It looks up
prebuilt responses keyed by SHA-256 of a canonicalised
``{model, system, messages}`` payload and returns token counts that match
Anthropic's real usage shape (``input_tokens``, ``output_tokens``,
``cache_read_input_tokens``, ``cache_creation_input_tokens``).

No live API calls are permitted in CI (LLM-05 contract). Every Claude-related
test in Plans 71-03..05 injects a ``FakeClaudeClient`` via constructor DI
instead of monkeypatching ``_build_client`` on the real extractor.

Public surface
--------------
>>> from tests.sentiment.fakes import FakeClaudeClient, prompt_sha
>>> fake = FakeClaudeClient()
>>> sha = prompt_sha("sys-prefix", [{"role": "user", "content": "body"}], "claude-haiku-4-5")
>>> fake.register_response(sha, [{"player_name": "Test"}])
>>> resp = fake.messages.create(
...     model="claude-haiku-4-5",
...     max_tokens=1024,
...     system="sys-prefix",
...     messages=[{"role": "user", "content": "body"}],
... )
>>> resp.content[0].text
'[{"player_name": "Test"}]'

The ``FakeClaudeClient`` intentionally satisfies the
``ClaudeClient`` Protocol from ``src/sentiment/processing/extractor.py`` by
exposing a ``messages`` attribute whose ``.create(...)`` accepts the same
keyword set as ``anthropic.Anthropic``.

Determinism contract (from Plan 71-02 action #4):
Response fixtures MUST be recorded with a frozen ``roster_provider=lambda: []``
so the SHA computation depends only on the static system prefix + the per-doc
user block. Plan 71-03's batched extractor tests MUST call
``extract_batch_primary(..., roster_provider=lambda: [])`` for the test /
benchmark paths so the computed SHA matches the fixture's ``prompt_sha``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SHA helper — module-level so tests and real fixtures share one implementation
# ---------------------------------------------------------------------------


def prompt_sha(system: Any, messages: Any, model: str) -> str:
    """Compute a canonical SHA-256 key for a Claude create(...) call.

    The canonicalisation is ``json.dumps({model, system, messages},
    sort_keys=True, default=str)`` then SHA-256 of the UTF-8 bytes. Sort
    keys + ``default=str`` make the key stable across dict reorderings and
    non-JSON-native objects (e.g. ``Path``, ``datetime``) that fixtures
    never exercise but that guard against incidental breakage.

    Args:
        system: The system prefix string (may be ``None``).
        messages: The list of ``{role, content}`` dicts sent to Claude.
        model: The Claude model identifier (e.g. ``"claude-haiku-4-5"``).

    Returns:
        64-character lowercase hex digest.
    """
    payload = json.dumps(
        {"model": model, "system": system, "messages": messages},
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Response-shape dataclasses — duck-type the real Anthropic SDK objects
# ---------------------------------------------------------------------------


@dataclass
class FakeUsage:
    """Mirrors ``anthropic.types.Usage`` shape used by the SDK.

    The four counters are exactly the fields the real SDK returns — no
    padding, no aliases — so cost-accounting code in Plan 71-03 that
    reads ``response.usage.input_tokens`` etc. works unchanged against
    both fakes and the real client.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeTextBlock:
    """Mirrors ``anthropic.types.TextBlock`` with just the ``.text`` field.

    The real SDK response content is ``list[ContentBlock]`` where the first
    (and usually only) block is a ``TextBlock`` with a ``.text`` attribute.
    Our consumers read ``response.content[0].text`` directly — this
    dataclass is the minimum viable shape.
    """

    text: str
    type: str = "text"


@dataclass
class FakeMessageResponse:
    """Mirrors the ``anthropic.types.Message`` response shape.

    The real SDK exposes many more fields (``id``, ``role``, ``model``,
    ``stop_reason``, etc.). We only populate ``content`` and ``usage``
    because those are the only two attributes the sentiment pipeline
    actually reads. Adding more fields should be a strict superset — no
    existing field rename.
    """

    content: List[FakeTextBlock]
    usage: FakeUsage = field(default_factory=FakeUsage)


# ---------------------------------------------------------------------------
# Messages surface
# ---------------------------------------------------------------------------


class FakeMessages:
    """Duck-type of ``anthropic.Anthropic().messages``.

    Exposes only ``.create(**kwargs)`` because that is the sole entry point
    the real extractor uses. The parent ``FakeClaudeClient`` owns the
    response registry and call log — ``FakeMessages`` is a thin dispatcher.
    """

    def __init__(self, parent: "FakeClaudeClient") -> None:
        """Initialise with a reference to the owning client."""
        self._parent = parent

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: Any = None,
        messages: Any = None,
        **kwargs: Any,
    ) -> FakeMessageResponse:
        """Look up a registered response by SHA and return it.

        Lookup precedence:
            1. Registered failure -> raise immediately (before responses).
            2. Registered response -> return stored text + usage.
            3. Strict=True -> AssertionError with diagnostic.
            4. Strict=False -> return empty-array stub with zero usage.

        Args:
            model: Claude model identifier. Included in SHA computation.
            max_tokens: Token ceiling. Stored in call_log but NOT in SHA
                (matching Anthropic caching semantics — same prompt, any
                max_tokens, one cache entry).
            system: System prefix string or list. Included in SHA.
            messages: List of role/content dicts. Included in SHA.
            **kwargs: Ignored but accepted to match SDK tolerance.

        Returns:
            A ``FakeMessageResponse`` matching the duck-type surface.

        Raises:
            AssertionError: if strict=True and no response is registered
                for the computed SHA. The message includes the computed
                SHA and the sorted list of registered keys for easy
                debugging.
            Exception: if the prompt was pre-registered via
                ``register_failure``. The exact exception instance passed
                to ``register_failure`` is re-raised.
        """
        sha = prompt_sha(system, messages, model)
        self._parent.call_log.append((sha, model, max_tokens))

        # Failures take precedence over responses so tests can layer them
        # unambiguously on the same key.
        if sha in self._parent._failures:
            raise self._parent._failures[sha]

        if sha in self._parent._responses:
            spec = self._parent._responses[sha]
            return FakeMessageResponse(
                content=[FakeTextBlock(text=spec["response_text"])],
                usage=FakeUsage(
                    input_tokens=spec["input_tokens"],
                    output_tokens=spec["output_tokens"],
                    cache_read_input_tokens=spec["cache_read_input_tokens"],
                    cache_creation_input_tokens=spec[
                        "cache_creation_input_tokens"
                    ],
                ),
            )

        if self._parent.strict:
            registered = sorted(self._parent._responses.keys())
            raise AssertionError(
                f"No FakeClaudeClient response registered for sha={sha}. "
                f"Registered: {registered}"
            )

        # Non-strict fallback: empty JSON array, zero usage.
        return FakeMessageResponse(
            content=[FakeTextBlock(text="[]")],
            usage=FakeUsage(),
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FakeClaudeClient:
    """Deterministic replacement for ``anthropic.Anthropic`` in tests.

    Satisfies the ``ClaudeClient`` Protocol from
    ``src/sentiment/processing/extractor.py`` via the public ``messages``
    attribute. Register responses (and optional failures) keyed by SHA-256
    of the outgoing prompt, then pass the fake into the batched extractor
    constructor.

    Attributes:
        messages: The ``FakeMessages`` dispatcher (satisfies the Protocol).
        call_log: List of ``(sha, model, max_tokens)`` tuples appended
            on every ``.messages.create(...)`` call. Tests use this to
            assert call counts and prompt stability.
        strict: When True (default), unregistered prompts raise
            ``AssertionError``. When False, unregistered prompts return
            an empty-array stub — useful when a test only cares about
            downstream fallback behaviour, not response content.

    Example:
        >>> fake = FakeClaudeClient()
        >>> sha = prompt_sha("sys", [{"role": "user", "content": "x"}], "m")
        >>> fake.register_response(sha, [{"player_name": "Test"}])
        >>> # Inject into the batched extractor (Plan 71-03):
        >>> # extractor = ClaudeBatchedExtractor(client=fake)
    """

    def __init__(self, strict: bool = True) -> None:
        """Initialise with empty registries.

        Args:
            strict: See class docstring. Defaults to True.
        """
        self.strict = strict
        self.messages = FakeMessages(self)
        self.call_log: List[Tuple[str, str, int]] = []
        self._responses: Dict[str, Dict[str, Any]] = {}
        self._failures: Dict[str, Exception] = {}

    # ------------------------------------------------------------------
    # Registration API
    # ------------------------------------------------------------------

    def register_response(
        self,
        prompt_key_or_sha: str,
        response_json: Union[List[Any], Dict[str, Any], str],
        input_tokens: int = 500,
        output_tokens: int = 200,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> None:
        """Register a canned response for a given prompt key.

        Args:
            prompt_key_or_sha: Either a 64-char hex SHA (returned by
                ``prompt_sha(...)``) or any arbitrary string. Tests may
                pass a pre-computed SHA OR a placeholder literal — both
                are valid keys. No normalisation is applied.
            response_json: The response body. If a ``list`` or ``dict``,
                it is serialised via ``json.dumps`` (Claude always returns
                a JSON array for extraction). If a ``str``, it is stored
                verbatim — useful for fixtures that intentionally carry
                markdown fences or pre-formatted text.
            input_tokens: Reported on ``response.usage.input_tokens``.
                Defaults to 500 — a realistic lower bound for a cached
                batched call of ~8 docs.
            output_tokens: Reported on ``response.usage.output_tokens``.
            cache_read_input_tokens: Reported on
                ``response.usage.cache_read_input_tokens``. Non-zero when
                the recorded call was a warm-cache hit.
            cache_creation_input_tokens: Reported on
                ``response.usage.cache_creation_input_tokens``. Non-zero
                when the recorded call created new cache content
                (typically the first call of the week).
        """
        if isinstance(response_json, str):
            response_text = response_json
        else:
            response_text = json.dumps(response_json)

        self._responses[prompt_key_or_sha] = {
            "response_text": response_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
        }

    def register_failure(
        self, prompt_key_or_sha: str, exc: Exception
    ) -> None:
        """Register an exception to raise on a given prompt key.

        Takes precedence over any registered response for the same key
        (see ``FakeMessages.create`` lookup order). Useful for testing
        the pipeline's per-doc soft fallback (Phase 71 D-06).

        Args:
            prompt_key_or_sha: Same keying rules as ``register_response``.
            exc: The exception instance to re-raise verbatim.
        """
        self._failures[prompt_key_or_sha] = exc

    # ------------------------------------------------------------------
    # Fixture loader
    # ------------------------------------------------------------------

    @classmethod
    def from_fixture_dir(
        cls, fixture_dir: Path, strict: bool = True
    ) -> "FakeClaudeClient":
        """Build a FakeClaudeClient from a directory of recorded fixtures.

        Walks every ``*.json`` file under ``fixture_dir`` (non-recursive —
        the fixture layout is flat) and registers each as a response using
        the file's ``prompt_sha`` field as the key plus the four token
        counts and the ``response_text``. Non-JSON files (e.g. README.md,
        stray editor artefacts) are silently skipped.

        Fixture file shape (see ``tests/fixtures/claude_responses/README.md``)::

            {
                "prompt_sha": "<64-hex or _PENDING_WAVE_2_SHA>",
                "model": "claude-haiku-4-5",
                "input_tokens": int,
                "output_tokens": int,
                "cache_read_input_tokens": int,
                "cache_creation_input_tokens": int,
                "response_text": "<JSON-encoded array as string>"
            }

        Args:
            fixture_dir: Directory containing recorded response fixtures.
            strict: Passed through to the new instance.

        Returns:
            A ``FakeClaudeClient`` pre-loaded with every fixture.

        Raises:
            FileNotFoundError: if ``fixture_dir`` does not exist.
        """
        if not fixture_dir.exists():
            raise FileNotFoundError(f"fixture dir not found: {fixture_dir}")

        fake = cls(strict=strict)
        for path in sorted(fixture_dir.glob("*.json")):
            try:
                spec = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "FakeClaudeClient.from_fixture_dir: skipping %s (%s)",
                    path.name,
                    exc,
                )
                continue

            sha = spec.get("prompt_sha")
            if not sha:
                logger.warning(
                    "FakeClaudeClient.from_fixture_dir: %s missing prompt_sha",
                    path.name,
                )
                continue

            fake.register_response(
                sha,
                spec.get("response_text", "[]"),
                input_tokens=int(spec.get("input_tokens", 0)),
                output_tokens=int(spec.get("output_tokens", 0)),
                cache_read_input_tokens=int(
                    spec.get("cache_read_input_tokens", 0)
                ),
                cache_creation_input_tokens=int(
                    spec.get("cache_creation_input_tokens", 0)
                ),
            )

        return fake


__all__ = [
    "FakeClaudeClient",
    "FakeMessages",
    "FakeMessageResponse",
    "FakeTextBlock",
    "FakeUsage",
    "prompt_sha",
]
