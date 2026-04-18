# Phase 61 — News & Sentiment Live: Context & Decisions

**Date:** 2026-04-17
**Captured from:** session discussion (post-phase-60)
**Status:** decisions locked — planner should respect these

---

## Core Architectural Decision: Rule-First, LLM Optional

The original roadmap framing implied the blocker for Phase 61 was missing `ANTHROPIC_API_KEY` in Railway. **That framing is rejected.** The API key was never the load-bearing piece; it was one implementation choice for ONE sub-problem (text-to-structured-signal extraction).

After re-thinking the problem, we split sentiment into two concerns with very different precision bars:

### Concern A: News SOURCES (fetching)
Decoupled from the key question entirely. Expanding sources is pure ingestion work and requires no LLM.

### Concern B: EXTRACTION (text → structured per-player signals)
The API key question lives here. The key insight: **model-facing extraction needs surgical precision; website-facing extraction can tolerate noise.** Treat them differently.

---

## Locked Decisions

### D-01: Source expansion via web-scraper agent (free, orthogonal to key)

Keep the existing 5 RSS feeds + Sleeper trending, and ADD:
- Reddit: `r/fantasyfootball`, `r/nfl`, `r/DynastyFF` via Reddit JSON API (free, no key)
- RotoWire news feed
- Pro Football Talk (PFT) articles
- Selected beat-writer feeds (Twitter/Bluesky public RSS bridges where available)

Ownership: `web-scraper` agent produces Bronze JSON documents matching the existing sentiment Bronze schema.

### D-02: Rule-based extractor is PRIMARY for model-facing signals

Expand `src/sentiment/processing/rule_extractor.py` (currently 279 lines, mostly injury-focused) to cover:
- **Injury events** (existing, keep): ruled_out, inactive, questionable, doubtful, IR, PUP, returning
- **Transaction events** (add): traded, released, signed, suspended, activated
- **Usage events** (add): "expected to start", "lead back", "splitting carries", "workhorse", "primary target", "limited snaps"
- **Weather events** (add): "game in doubt", "blizzard", "high winds", numeric wind/precipitation thresholds

Why rules-only for the model path:
- Deterministic → reproducible backtests (Phase 54 WFCV/production lesson)
- Very high precision on stable journalistic phrasing
- Zero variance from LLM non-determinism
- No external dependency, no rate limits, no cost

### D-03: Wire model via structured EVENTS, not continuous sentiment

**Do NOT feed a numerical `sentiment_multiplier` (0.70–1.15 range) into the projection engine.** That range is too wide and too vague — it will introduce projection noise that exceeds the signal it provides (see Phase 54: WFCV often shows improvement that does not survive in production).

Instead:
- Extend the existing `apply_injury_adjustments()` pattern in `src/projection_engine.py`
- Add a companion `apply_event_adjustments()` that keys on structured event flags
- Each event maps to a deterministic, tightly-bounded multiplier (e.g., `is_questionable` → 0.85, `is_returning_from_ir` → 0.90 in the return week, etc.)
- MUST backtest (2022–2024, half_ppr) before shipping to production projections — SHIP only if MAE does not regress vs baseline

### D-04: Claude Haiku is OPTIONAL website enrichment behind a feature flag

Claude Haiku stays in the codebase but becomes non-load-bearing:
- Used ONLY for website-facing news enrichment (1-sentence summary, category tag where rules missed)
- Degrades gracefully when `ANTHROPIC_API_KEY` is unset — website still shows raw article title, source, date, and any rule-extracted event tags
- Feature-flagged via environment variable (e.g., `ENABLE_LLM_ENRICHMENT=false` by default)
- Never touches the model path

Why keep it at all: at real volume (~100 articles/day), Haiku costs ~$1–5/month. Rule extractor cannot reliably generate human-readable 1-sentence summaries. The free alternatives (local Llama via Ollama) introduce ops overhead disproportionate to the savings.

### D-05: Do NOT introduce Ollama or local LLM infrastructure in this phase

Considered and rejected:
- Structured JSON extraction on local small models (Llama 3 7B/8B) has high rates of player-name hallucination and invented event flags
- Adds a server dependency (Ollama), model weights to manage, CPU/GPU capacity to plan
- Rule extractor gives deterministic correctness; if we need more coverage, we add more rules, not more LLM

If local LLM ever becomes interesting, it's a separate future phase.

### D-06: Daily cron runs the full pipeline, rule-only path is never blocked

The daily GitHub Actions cron (per NEWS-01) runs:
1. Source ingestion (all free sources, including new Reddit/RotoWire/PFT)
2. Rule-extraction over Bronze → Silver (NEVER blocked by missing API key)
3. Weekly aggregation Silver → Gold
4. Event-based projection adjustments
5. **Optional:** if `ENABLE_LLM_ENRICHMENT=true`, run Haiku enrichment as a post-step for website display only

Missing API key = missing LLM summaries on website only. Never breaks the pipeline, never breaks the model path.

---

## Success Criteria Interpretation

Mapping the ROADMAP's four SCs to these decisions:

| SC # | Roadmap text | Rule-first interpretation |
|------|--------------|---------------------------|
| 1 | Daily sentiment pipeline runs automatically via cron and processes RSS, Sleeper, and Reddit sources | Cron runs rule-extraction over RSS + Sleeper + Reddit + RotoWire + PFT; pipeline succeeds without API key |
| 2 | News page displays real articles with source attribution, publication date, and tagged player names | Website shows raw article metadata + rule-extracted player tags + event badges (injury/trade/usage) |
| 3 | Team sentiment dashboard shows all 32 teams in color-coded grid | Team-level "event density" score — aggregates structured events per team (e.g., high injury count = red) rather than continuous sentiment score |
| 4 | Player detail page shows bullish/bearish sentiment badges | Badges derived from event flags (e.g., "Questionable" badge, "Returning" badge, "Trade rumor" badge) — NOT a numerical sentiment score |

---

## Out of Scope for Phase 61

- Neo4j sentiment graph (already deferred to perfect-impl vision)
- Paid source integration (Pro Football Focus, Rotoworld premium) — perfect-impl vision
- Continuous (−1 to +1) sentiment scoring in any production path
- Local LLM infrastructure

## References

- `src/sentiment/processing/rule_extractor.py` — existing 279-line rule extractor (expand this)
- `src/sentiment/processing/extractor.py` — existing Claude Haiku extractor (demote to optional website path)
- `src/projection_engine.py::apply_injury_adjustments` — existing pattern to extend for `apply_event_adjustments`
- Memory: `project_phase_60_data_quality.md` — shipped 2026-04-17
- Memory: `MEMORY.md` sentiment pipeline section — describes current blocked-on-key state; supersede with this phase
