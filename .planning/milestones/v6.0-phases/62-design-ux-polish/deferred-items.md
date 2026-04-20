# Phase 62 — Deferred Items

Items discovered during plan execution that fall outside the owning plan's scope.
Each entry lists where it was found, what it is, and a recommended owner.

---

## 62-02 execution — 2026-04-17

### Root .gitignore has an over-broad Python template rule that hides frontend source

**Where found:** Attempting `git add web/frontend/src/lib/design-tokens.ts` during plan 62-02 task 2 commit.

**Issue:** The root `.gitignore` line `lib/` (from the Python packaging template, lines 51-53) pattern-matches `web/frontend/src/lib/`. Only `web/frontend/src/lib/nfl/api.ts` and `web/frontend/src/lib/nfl/types.ts` are currently git-tracked — those predated the rule or were `git add -f`'d. All of the following load-bearing frontend source files are on disk, referenced by the Next.js app (the `npm run build` during 62-02 succeeded), but NOT tracked in git:

- `web/frontend/src/lib/api-client.ts`
- `web/frontend/src/lib/compose-refs.ts`
- `web/frontend/src/lib/data-table.ts`
- `web/frontend/src/lib/format.ts`
- `web/frontend/src/lib/nfl/team-colors.ts`
- `web/frontend/src/lib/nfl/team-meta.ts`
- `web/frontend/src/lib/parsers.ts`
- `web/frontend/src/lib/query-client.ts`
- `web/frontend/src/lib/searchparams.ts`
- `web/frontend/src/lib/utils.ts`

This means the frontend depends on files that are not under version control and not deployable from a fresh clone.

**62-02 mitigation:** Added a targeted un-ignore (`!web/frontend/src/lib/` + `!web/frontend/src/lib/**`) so `design-tokens.ts` can be committed. This un-ignore ALSO reveals the 10 untracked files above; however they are NOT staged by 62-02 because the plan's `files_modified` contract only covers tokens/docs.

**Recommended owner:** Phase 62-03 (it already owns POSITION_COLORS migration which will touch several of these files) OR a separate chore plan. Action needed: `git add` the 10 files above in a single `chore(62): track frontend src/lib source files` commit. Verify build still succeeds afterward.

**Risk if ignored:** Every CI clone depends on developer-local filesystem state. Vercel deployment will break if Vercel's build checkout doesn't already have these files (they may be on disk because they were never removed, or they may be copied in during `npm install` — worth checking).
