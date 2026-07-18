# Monitor catalog — Snowflake SQL + dbt checks

Concrete checks for each signal. Run them in the GitHub Actions step after the pipeline; on a tripped
threshold, hand a structured payload to the sender in `routing-slack-email.md`. All SQL is Snowflake.

## Freshness / staleness
dbt source freshness (declarative — preferred when sources are in dbt):
```yaml
# models/sources.yml
sources:
  - name: raw
    loaded_at_field: _loaded_at
    freshness:
      warn_after:  {count: 6,  period: hour}
      error_after: {count: 24, period: hour}
    tables: [{name: orders}]
```
`dbt source freshness` then exits non-zero / writes `sources.json` you can parse. Ad-hoc SQL version:
```sql
select datediff('hour', max(_loaded_at), current_timestamp()) as hours_stale
from raw.orders;          -- alert if hours_stale > sla
```

## Volume anomaly (0 rows is the classic outage)
```sql
with today as (select count(*) n from analytics.daily_fact where dt = current_date()),
     base  as (select median(n) med from (
        select dt, count(*) n from analytics.daily_fact
        where dt >= dateadd('day', -28, current_date()) group by dt))
select t.n, b.med,
       case when t.n = 0 then 'critical'
            when abs(t.n - b.med) / nullif(b.med,0) > 0.5 then 'warning'
            else 'ok' end as status
from today t cross join base b;
```
Tune the band per table; seasonal data needs day-of-week-aware baselines.

## Schema drift
Snapshot `information_schema.columns` and diff against the last known-good:
```sql
select column_name, data_type
from information_schema.columns
where table_schema = 'RAW' and table_name = 'ORDERS'
order by ordinal_position;
```
Store the result each run; alert on added/removed/retyped columns. (dbt contracts can enforce this at
build time — pair with `data-quality`.)

## Quality-gate failure (alert on dbt test / assertion results)
`dbt test` / `dbt build` writes `target/run_results.json`. Parse it and alert on failures:
```python
import json
rr = json.load(open("target/run_results.json"))
failed = [r for r in rr["results"] if r["status"] in ("fail", "error")]
# -> build payloads: node = r["unique_id"], message = r.get("message")
```

## Dead-man's-switch (the job never ran)
The check that lives *outside* the job, so a job that never starts still alerts:
- **Heartbeat:** on success, ping a watchdog (`curl -fsS https://hc-ping.com/<uuid>`); the watchdog
  pages if no ping arrives within the window. Zero infra to run.
- **Self-query** (separate schedule): "did a run land recently?"
```sql
select case when max(run_finished_at) < dateadd('hour', -26, current_timestamp())
            then 'critical' else 'ok' end as status
from ops.pipeline_runs where pipeline = 'orders_daily';
```

## Runtime / cost spike (Snowflake)
```sql
select query_id, total_elapsed_time/1000 as secs,
       credits_used_cloud_services
from snowflake.account_usage.query_history
where start_time > dateadd('day', -1, current_timestamp())
order by secs desc limit 20;   -- alert if top run >> trailing baseline
```

## Hysteresis (don't flap)
Require **N consecutive** breaches before firing, and emit a **recovered** message when it clears:
```python
state = load_state()                      # e.g. a small JSON/table of {check: consecutive_fails}
state[check] = state.get(check, 0) + 1 if tripped else 0
if state[check] == N_CONSECUTIVE: fire(check, "critical")
if state[check] == 0 and was_firing(check): fire(check, "recovered")
save_state(state)
```
