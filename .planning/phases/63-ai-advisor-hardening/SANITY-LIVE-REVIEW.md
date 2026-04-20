# Code Review: --check-live flag (commit 74f23cd)

## 1. HTTP Timeouts

Sensible. Backend probes use `timeout=15`; frontend probes use `timeout=20` (extra 5s
for auth-redirect round-trips). Both are well below any CI job limit and above typical
Railway cold-start latency (~8s). No concern.

## 2. Infinite Loops / Unhandled Exceptions

None. The probe loop is a bounded `for` over a fixed list. Every network call is wrapped
in `except requests.RequestException`, and `resp.json()` is guarded by `except ValueError`.
Control always reaches `continue` or the pass-through. Clean.

## 3. Skeleton-Forever Frontend Gap (CONFIRMED — flag)

The comment in the code correctly identifies this as a known limitation, but the check
still does not catch it. Next.js SSR returns skeleton `<div>` placeholders in the
initial HTML; those divs contain the word "Projections" (via aria-label or nearby
heading), so `required_markers` passes even when the client bundle never hydrates.
The only reliable detection would be a headless-browser check (Playwright) that waits
for the skeleton class to disappear. This is a gap worth tracking; the current check
catches 5xx and blank bodies, not silent client-side hydration failures.

## 4. Validator Lambdas on Unexpected Payloads

Three of the four lambdas call `.get()` on `d`, which is safe against any dict-like
payload. The projection lambda does `d["projections"]` after `d.get("projections")`
returns a truthy list — fine. The one risk: if the API returns a non-dict JSON value
(e.g., a bare list or string), `d.get(...)` raises `AttributeError`. This is not
guarded. Recommend wrapping the validator call: `isinstance(payload, dict) and
validator(payload)` before invoking the lambda.

## 5. CLI Arg Collisions

`--check-live`, `--live-backend-url`, `--live-frontend-url` are new and unique. No
collision with existing args (`--scoring`, `--season`, `--week`, `--check-predictions`,
`--all`). The `--all` dest override (`dest="check_all"`) predates this commit and is
unaffected.

## Verdict

PASS with two notes:
- **Gap (non-blocking)**: Skeleton-forever bug is not caught; Playwright probe needed.
- **Low-risk bug**: Non-dict JSON payload causes `AttributeError` in validator lambda;
  add `isinstance(payload, dict)` guard before calling validator.
