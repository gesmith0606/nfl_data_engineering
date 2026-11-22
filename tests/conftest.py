"""Suite-wide fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_llm_cost_ledger(tmp_path_factory, monkeypatch):
    """Keep test runs out of the tracked LLM cost ledger.

    ``SentimentPipeline`` builds a default ``CostLog()`` when none is injected,
    and that default is ``data/ops/llm_costs/`` -- a tracked directory. Tests
    that drove the pipeline with a fake Claude client wrote one fake record
    per call there (500 in / 200 out tokens, $0.0015); 188 of them were
    committed as if they were production telemetry. Every test now gets a
    throwaway ledger unless it passes its own ``base_dir``.
    """
    monkeypatch.setenv("LLM_COST_LOG_DIR", str(tmp_path_factory.mktemp("llm_costs")))
