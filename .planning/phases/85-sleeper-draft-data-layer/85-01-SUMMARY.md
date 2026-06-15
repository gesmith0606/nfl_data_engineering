# 85-01 Summary

Shipped (commit afc1315): Sleeper draft endpoints on `src/sleeper_http.py`
(`get_user`, `get_user_drafts`, `get_drafts_for_league`, `get_draft`,
`get_draft_picks`, `get_traded_picks`, fail-open list/dict-normalized) +
`src/draft_models.py` neutral `PickEvent`/`DraftState` + `src/sleeper_draft.py`
`pick_from_sleeper`/`state_from_sleeper`/`load_draft_state`. Fixture + offline tests.
Requirements: SLPR-01, SLPR-04. ✓
