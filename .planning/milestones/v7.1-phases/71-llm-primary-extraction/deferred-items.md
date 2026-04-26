
## Deferred (out-of-scope for Plan 71-04)

- **tests/test_daily_pipeline.py::TestFailureIsolation::test_all_fail_returns_exit_code_1** — pre-existing failure verified against baseline commit 18593fd (pre-71-04). Test mocks "mock" step names but RotoWire/PFT/LLM Enrichment run for real and return success because they aren't being patched. Not introduced by Plan 71-04. File a separate ticket if needed.

## Deferred (out-of-scope for Plan 71-05)

- **Live Bronze writes from `tests/sentiment/test_ingest_pft.py` + `test_ingest_rotowire.py`** — running the full sentiment suite produces real `data/bronze/sentiment/{pft,rotowire}/season=2025/*.json` files because those ingestion tests hit live RSS feeds and don't redirect their output dir to `tmp_path`. Pre-existing (not introduced by Plan 71-05). Retrofit candidate: `monkeypatch.setattr(module, "_BRONZE_DIR", tmp_path)` (mirrors Plan 71-04's pipeline test convention). Filing a separate ticket if the noise becomes problematic.
