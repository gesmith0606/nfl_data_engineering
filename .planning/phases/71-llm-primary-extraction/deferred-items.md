
## Deferred (out-of-scope for Plan 71-04)

- **tests/test_daily_pipeline.py::TestFailureIsolation::test_all_fail_returns_exit_code_1** — pre-existing failure verified against baseline commit 18593fd (pre-71-04). Test mocks "mock" step names but RotoWire/PFT/LLM Enrichment run for real and return success because they aren't being patched. Not introduced by Plan 71-04. File a separate ticket if needed.
