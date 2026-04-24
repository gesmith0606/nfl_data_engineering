"""Tests for the deterministic FakeClaudeClient harness (Plan 71-02).

The FakeClaudeClient is the replay-only double that powers every
Claude-related test in Plans 71-03..05. It duck-types
``anthropic.Anthropic`` via a ``.messages.create(...)`` surface and looks
up prebuilt responses keyed by SHA-256 of a canonicalised
``{model, system, messages}`` payload. No live API calls permitted
in CI (LLM-05 contract).

Task 1 tests (8 behaviours from the Plan):
    1. Instantiation — empty call_log, has ``.messages`` attribute.
    2. register_response + matching SHA -> correct JSON text returned.
    3. Unregistered prompt in strict mode -> AssertionError with SHA
       + registered list in diagnostic.
    4. register_failure -> registered exception raised on call.
    5. Token accounting on ``response.usage``.
    6. call_log is a list of ``(sha, model, max_tokens)`` tuples.
    7. from_fixture_dir walks *.json files and loads them.
    8. from_fixture_dir registers non-strict mode stub on miss.

Task 3 tests (appended to this file, per plan):
    9. from_fixture_dir against real tests/fixtures/claude_responses/.
    10. from_fixture_dir skips README.md without error.
    11. Placeholder _PENDING_WAVE_2_SHA loaded but unusable strictly.
    12. call_log grows monotonically on successive calls.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_prompt_args() -> Dict[str, Any]:
    """Return a minimal create(...) kwargs bundle used across tests."""
    return {
        "model": "claude-haiku-4-5",
        "max_tokens": 1024,
        "system": "You are an NFL extractor.",
        "messages": [{"role": "user", "content": "Travis Kelce ruled out."}],
    }


# ---------------------------------------------------------------------------
# Task 1 — 8 core behaviours
# ---------------------------------------------------------------------------


class FakeClaudeClientConstructionTests(unittest.TestCase):
    """Test 1: basic instantiation shape."""

    def test_instantiates_with_empty_call_log_and_messages_attr(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient

        fake = FakeClaudeClient()
        self.assertEqual(fake.call_log, [])
        self.assertTrue(hasattr(fake, "messages"))
        self.assertTrue(hasattr(fake.messages, "create"))


class RegisterResponseTests(unittest.TestCase):
    """Test 2: register_response + matching SHA -> correct response text."""

    def test_matching_sha_returns_registered_response_text(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient()
        args = _sample_prompt_args()
        sha = prompt_sha(args["system"], args["messages"], args["model"])
        fake.register_response(sha, [{"player_name": "Test"}])

        resp = fake.messages.create(**args)
        expected_text = json.dumps([{"player_name": "Test"}])
        self.assertEqual(resp.content[0].text, expected_text)

    def test_raw_string_response_is_stored_verbatim(self) -> None:
        """Passing a raw string keeps markdown fences / preformatted text."""
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient()
        args = _sample_prompt_args()
        sha = prompt_sha(args["system"], args["messages"], args["model"])
        fenced = '```json\n[{"player_name": "Test"}]\n```'
        fake.register_response(sha, fenced)

        resp = fake.messages.create(**args)
        self.assertEqual(resp.content[0].text, fenced)


class StrictModeUnregisteredPromptTests(unittest.TestCase):
    """Test 3: unregistered prompt in strict mode raises diagnostic assertion."""

    def test_unregistered_prompt_in_strict_mode_raises_assertion(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient(strict=True)
        # Register a dummy key so we can verify the diagnostic lists it.
        fake.register_response("a" * 64, [])

        args = _sample_prompt_args()
        computed = prompt_sha(args["system"], args["messages"], args["model"])

        with self.assertRaises(AssertionError) as ctx:
            fake.messages.create(**args)

        msg = str(ctx.exception)
        self.assertIn(computed, msg)
        self.assertIn("a" * 64, msg)

    def test_unregistered_prompt_in_nonstrict_mode_returns_empty_array(
        self,
    ) -> None:
        from tests.sentiment.fakes import FakeClaudeClient

        fake = FakeClaudeClient(strict=False)
        args = _sample_prompt_args()
        resp = fake.messages.create(**args)

        self.assertEqual(resp.content[0].text, "[]")
        self.assertEqual(resp.usage.input_tokens, 0)
        self.assertEqual(resp.usage.output_tokens, 0)


class RegisterFailureTests(unittest.TestCase):
    """Test 4: register_failure -> registered exception raised on call."""

    def test_registered_failure_raises_exception(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient()
        args = _sample_prompt_args()
        sha = prompt_sha(args["system"], args["messages"], args["model"])
        fake.register_failure(sha, RuntimeError("boom"))

        with self.assertRaises(RuntimeError) as ctx:
            fake.messages.create(**args)

        self.assertEqual(str(ctx.exception), "boom")

    def test_failure_takes_precedence_over_registered_response(self) -> None:
        """Failure lookup happens BEFORE response lookup."""
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient()
        args = _sample_prompt_args()
        sha = prompt_sha(args["system"], args["messages"], args["model"])
        fake.register_response(sha, [{"player_name": "Test"}])
        fake.register_failure(sha, ValueError("failure wins"))

        with self.assertRaises(ValueError):
            fake.messages.create(**args)


class TokenAccountingTests(unittest.TestCase):
    """Test 5: usage reflects register_response token kwargs."""

    def test_usage_reflects_registered_token_counts(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient()
        args = _sample_prompt_args()
        sha = prompt_sha(args["system"], args["messages"], args["model"])
        fake.register_response(
            sha,
            [],
            input_tokens=1243,
            output_tokens=487,
            cache_read_input_tokens=1100,
            cache_creation_input_tokens=0,
        )

        resp = fake.messages.create(**args)
        self.assertEqual(resp.usage.input_tokens, 1243)
        self.assertEqual(resp.usage.output_tokens, 487)
        self.assertEqual(resp.usage.cache_read_input_tokens, 1100)
        self.assertEqual(resp.usage.cache_creation_input_tokens, 0)


class CallLogTests(unittest.TestCase):
    """Test 6: call_log is a list of (sha, model, max_tokens) tuples."""

    def test_call_log_appends_tuple_per_call(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient()
        args = _sample_prompt_args()
        sha = prompt_sha(args["system"], args["messages"], args["model"])
        fake.register_response(sha, [])

        fake.messages.create(**args)
        self.assertEqual(len(fake.call_log), 1)
        entry = fake.call_log[0]
        self.assertEqual(entry, (sha, args["model"], args["max_tokens"]))


class FromFixtureDirTests(unittest.TestCase):
    """Test 7: from_fixture_dir walks *.json, registers by prompt_sha."""

    def test_loads_json_files_and_registers_by_prompt_sha(self) -> None:
        import tempfile

        from tests.sentiment.fakes import FakeClaudeClient

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "batch_a.json").write_text(
                json.dumps(
                    {
                        "prompt_sha": "sha-a",
                        "model": "claude-haiku-4-5",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "response_text": "[]",
                    }
                )
            )
            (tmp / "batch_b.json").write_text(
                json.dumps(
                    {
                        "prompt_sha": "sha-b",
                        "model": "claude-haiku-4-5",
                        "input_tokens": 200,
                        "output_tokens": 75,
                        "cache_read_input_tokens": 180,
                        "cache_creation_input_tokens": 0,
                        "response_text": '[{"player_name":"Jalen Hurts"}]',
                    }
                )
            )

            fake = FakeClaudeClient.from_fixture_dir(tmp)

            # Internal store holds both keys.
            self.assertIn("sha-a", fake._responses)
            self.assertIn("sha-b", fake._responses)


class NonStrictEmptyResponseTests(unittest.TestCase):
    """Test 8: non-strict mode stub carries zero usage."""

    def test_non_strict_stub_has_zero_usage_counts(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient

        fake = FakeClaudeClient(strict=False)
        resp = fake.messages.create(**_sample_prompt_args())

        self.assertEqual(resp.usage.input_tokens, 0)
        self.assertEqual(resp.usage.output_tokens, 0)
        self.assertEqual(resp.usage.cache_read_input_tokens, 0)
        self.assertEqual(resp.usage.cache_creation_input_tokens, 0)


# ---------------------------------------------------------------------------
# Task 3 — wire FakeClaudeClient.from_fixture_dir to real fixtures
# ---------------------------------------------------------------------------


class FromFixtureDirRealFixturesTests(unittest.TestCase):
    """Test 9: loads the actual tests/fixtures/claude_responses/ set."""

    def test_loads_offseason_w17_and_w18_fixtures(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient

        fixtures_dir = _PROJECT_ROOT / "tests" / "fixtures" / "claude_responses"
        self.assertTrue(
            fixtures_dir.exists(), f"missing fixture dir: {fixtures_dir}"
        )
        fake = FakeClaudeClient.from_fixture_dir(fixtures_dir)
        # At least W17 + W18 fixtures are loaded (README.md must be skipped).
        self.assertGreaterEqual(len(fake._responses), 2)


class FromFixtureDirSkipsReadmeTests(unittest.TestCase):
    """Test 10: README.md in fixture dir is skipped cleanly."""

    def test_readme_is_skipped_without_error(self) -> None:
        import tempfile

        from tests.sentiment.fakes import FakeClaudeClient

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "README.md").write_text("# fixtures\n\nNot JSON.\n")
            (tmp / "only_one.json").write_text(
                json.dumps(
                    {
                        "prompt_sha": "sha-only",
                        "model": "claude-haiku-4-5",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "response_text": "[]",
                    }
                )
            )

            fake = FakeClaudeClient.from_fixture_dir(tmp)
            self.assertEqual(len(fake._responses), 1)
            self.assertIn("sha-only", fake._responses)


class PlaceholderShaWorkflowTests(unittest.TestCase):
    """Test 11: placeholder _PENDING_WAVE_2_SHA loaded but unusable strictly."""

    def test_placeholder_sha_loads_but_real_call_raises(self) -> None:
        import tempfile

        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "pending.json").write_text(
                json.dumps(
                    {
                        "prompt_sha": "_PENDING_WAVE_2_SHA",
                        "model": "claude-haiku-4-5",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "response_text": "[]",
                    }
                )
            )

            fake = FakeClaudeClient.from_fixture_dir(tmp, strict=True)
            self.assertIn("_PENDING_WAVE_2_SHA", fake._responses)

            args = _sample_prompt_args()
            real_sha = prompt_sha(
                args["system"], args["messages"], args["model"]
            )

            with self.assertRaises(AssertionError) as ctx:
                fake.messages.create(**args)

            msg = str(ctx.exception)
            # Diagnostic lists the placeholder as a registered key.
            self.assertIn("_PENDING_WAVE_2_SHA", msg)
            self.assertIn(real_sha, msg)


class CallLogGrowthTests(unittest.TestCase):
    """Test 12: call_log grows monotonically across multiple calls."""

    def test_three_calls_produce_three_log_entries(self) -> None:
        from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

        fake = FakeClaudeClient()

        for i in range(3):
            args = _sample_prompt_args()
            args["messages"] = [{"role": "user", "content": f"doc {i}"}]
            sha = prompt_sha(args["system"], args["messages"], args["model"])
            fake.register_response(sha, [])
            fake.messages.create(**args)

        self.assertEqual(len(fake.call_log), 3)
        for entry in fake.call_log:
            self.assertEqual(len(entry), 3)
            sha, model, max_tokens = entry
            self.assertIsInstance(sha, str)
            self.assertEqual(model, "claude-haiku-4-5")
            self.assertEqual(max_tokens, 1024)


if __name__ == "__main__":
    unittest.main()
