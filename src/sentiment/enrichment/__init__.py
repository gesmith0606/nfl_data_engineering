"""Optional LLM enrichment for the NFL Sentiment Pipeline.

This package is strictly website-only and MUST NOT feed the model path
(Phase 61 D-02 / D-04). It adds a 1-sentence ``summary`` and a
``refined_category`` tag to Silver signal records for nicer news cards,
and degrades gracefully when ``ANTHROPIC_API_KEY`` is unset or the
``anthropic`` SDK is not importable.
"""

from src.sentiment.enrichment.llm_enrichment import (
    LLMEnrichment,
    enrich_silver_records,
)

__all__ = ["LLMEnrichment", "enrich_silver_records"]
