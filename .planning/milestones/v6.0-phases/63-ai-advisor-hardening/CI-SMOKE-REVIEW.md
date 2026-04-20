# CI Smoke Gate Review — commit 938b62f

## 1. `needs` + `if` condition logic

The condition `always() && (needs.deploy-frontend.result == 'success' || needs.deploy-backend.result == 'success')` is **correct** for the stated intent: the job runs whenever the workflow reaches this point AND at least one deploy succeeded. `always()` prevents GitHub from skipping the job when an upstream dependency fails; the OR guard ensures a fully-failed deploy pair does not trigger a pointless smoke run. No fix needed.

## 2. Dependency install

`pip install requests` is correct and sufficient. `sanity_check_projections.py --check-live` issues HTTP probes; it does not load parquet/pandas in live mode. Caching against `requirements.txt` is a minor inefficiency (the hash will change on any dep bump even though `requests` is pinned implicitly), but it is harmless and still faster than a cold install.

## 3. 45s propagation wait

**Marginal risk.** Railway container restarts typically finish in 20-30s, but cold-start + Railway router drain under load can push beyond 45s. Vercel edge propagation is usually under 10s. The wait is adequate for happy-path deploys; a flaky cold-start could produce a false-negative smoke failure. Consider bumping to 60s or adding a retry loop in the script itself before treating this as a hard blocker.

## 4. Exit-code propagation

The step has no `continue-on-error` override and no explicit `|| true`. A non-zero exit from `sanity_check_projections.py` will fail the step, which fails the job, which marks the workflow run as failed. Propagation is correct.

## 5. YAML syntax

No issues. Indentation is consistent (2-space), multi-line `run` block uses correct `|` scalar, inline comment on the last line is valid YAML. The job will parse without error.

## Verdict

PASS with one advisory: bump the propagation wait from 45s to 60s to absorb Railway cold-start variance before this gate reaches production traffic.
