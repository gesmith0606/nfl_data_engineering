---
phase: SV2-daily-automation
plan: 04
type: execute
wave: 3
depends_on: [SV2-01, SV2-02]
files_modified:
  - scripts/daily_sentiment_pipeline.py
  - .github/workflows/daily-sentiment.yml
  - scripts/process_sentiment.py
autonomous: true
requirements: [SV2-14, SV2-15, SV2-16]

must_haves:
  truths:
    - "A single script runs the full daily sentiment pipeline: ingest all sources, extract, aggregate player + team"
    - "GitHub Actions cron runs the daily pipeline automatically"
    - "Pipeline is idempotent (re-running same day does not duplicate data)"
  artifacts:
    - path: "scripts/daily_sentiment_pipeline.py"
      provides: "Orchestrator for daily ingestion + extraction + aggregation"
      contains: "argparse"
    - path: ".github/workflows/daily-sentiment.yml"
      provides: "GitHub Actions daily cron workflow"
      contains: "schedule"
  key_links:
    - from: "scripts/daily_sentiment_pipeline.py"
      to: "scripts/ingest_sentiment_rss.py"
      via: "subprocess or direct import"
      pattern: "ingest.*rss"
    - from: "scripts/daily_sentiment_pipeline.py"
      to: "scripts/ingest_sentiment_reddit.py"
      via: "subprocess or direct import"
      pattern: "ingest.*reddit"
    - from: "scripts/daily_sentiment_pipeline.py"
      to: "scripts/process_sentiment.py"
      via: "subprocess or direct import"
      pattern: "process_sentiment"
---

<objective>
Create a daily automation script and GitHub Actions cron job that runs the full
sentiment pipeline (ingest -> extract -> aggregate) automatically.

Purpose: Sentiment data is only valuable if it's fresh. A daily cron ensures news
and sentiment signals are always up-to-date without manual intervention.

Output: Daily pipeline orchestrator script, GitHub Actions workflow.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/sentiment-v2/SV2-01-SUMMARY.md
@.planning/phases/sentiment-v2/SV2-02-SUMMARY.md

@scripts/ingest_sentiment_rss.py
@scripts/ingest_sentiment_sleeper.py
@scripts/process_sentiment.py
@.github/workflows/weekly-pipeline.yml

<interfaces>
<!-- Existing CLI scripts to orchestrate -->
```bash
# Step 1: Ingest from all sources
python scripts/ingest_sentiment_rss.py --season 2026
python scripts/ingest_sentiment_reddit.py --season 2026
python scripts/ingest_sentiment_sleeper.py --season 2026

# Step 2: Extract + aggregate (player + team)
python scripts/process_sentiment.py --season 2026 --week 1
```

<!-- Existing GitHub Actions pattern (.github/workflows/weekly-pipeline.yml) -->
```yaml
on:
  schedule:
    - cron: '0 9 * * 2'  # Tuesday 9am UTC
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Daily pipeline orchestrator script</name>
  <files>scripts/daily_sentiment_pipeline.py</files>
  <action>
    Create `scripts/daily_sentiment_pipeline.py` that runs the full daily pipeline:

    1. **Auto-detect season and week**: Use current date to determine NFL season/week
       (reuse the logic from the weekly-pipeline GHA or write a simple helper:
       season starts in September, week 1 is first Thursday, each week is 7 days).
       Support `--season` and `--week` overrides.

    2. **Ingestion phase** (parallel-safe, idempotent):
       - Run RSS ingestion: import and call the ingest function from `ingest_sentiment_rss.py`
       - Run Reddit ingestion: import and call from `ingest_sentiment_reddit.py`
       - Run Sleeper ingestion: import and call from `ingest_sentiment_sleeper.py`
       - Each ingestion writes timestamped files, so re-runs produce new files (no duplicates
         because downstream dedup uses `processed_ids.json`)

    3. **Extraction phase**:
       - Import `SentimentPipeline` from `src.sentiment.processing.pipeline`
       - Run in "auto" mode (rule-based by default, Claude if API key available)
       - Pipeline tracks processed doc IDs, so re-runs skip already-processed docs

    4. **Aggregation phase**:
       - Run player-level weekly aggregation (existing `WeeklyAggregator`)
       - Run team-level weekly aggregation (new `TeamWeeklyAggregator`)
       - Both overwrite their output Parquet (latest wins)

    5. **Summary output**:
       - Print: sources ingested, documents processed, signals extracted, teams aggregated
       - Exit code 0 on success, 1 on any failure (with error details)

    6. **Flags**: `--season`, `--week`, `--verbose`, `--dry-run` (shows what would run), `--skip-ingest` (for re-processing only)

    Follow the existing script patterns (argparse, logging, sys.path bootstrap).
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python scripts/daily_sentiment_pipeline.py --dry-run --verbose 2>&1 | head -20</automated>
  </verify>
  <done>
    - Script runs end-to-end with --dry-run showing all steps
    - Idempotent: re-running same day skips already-processed documents
    - Auto-detects season and week from current date
    - Exits with code 0 on success
  </done>
</task>

<task type="auto">
  <name>Task 2: GitHub Actions daily cron workflow</name>
  <files>.github/workflows/daily-sentiment.yml</files>
  <action>
    Create `.github/workflows/daily-sentiment.yml` following the pattern of the existing
    `weekly-pipeline.yml`:

    ```yaml
    name: Daily Sentiment Pipeline
    on:
      schedule:
        - cron: '0 12 * * *'  # Daily at noon UTC (7am ET)
      workflow_dispatch:  # Manual trigger
        inputs:
          season:
            description: 'NFL season year'
            required: false
          week:
            description: 'NFL week number'
            required: false

    jobs:
      sentiment:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with:
              python-version: '3.11'
              cache: 'pip'
          - run: pip install -r requirements.txt
          - name: Run daily sentiment pipeline
            env:
              ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
            run: |
              python scripts/daily_sentiment_pipeline.py \
                ${{ inputs.season && format('--season {0}', inputs.season) || '' }} \
                ${{ inputs.week && format('--week {0}', inputs.week) || '' }} \
                --verbose
          - name: Open issue on failure
            if: failure()
            uses: actions/github-script@v7
            with:
              script: |
                github.rest.issues.create({
                  owner: context.repo.owner,
                  repo: context.repo.repo,
                  title: `Daily Sentiment Pipeline Failed - ${new Date().toISOString().split('T')[0]}`,
                  body: `Workflow run: ${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,
                  labels: ['pipeline-failure']
                })
    ```

    Key design choices:
    - ANTHROPIC_API_KEY is optional (pipeline falls back to rule-based)
    - Daily at noon UTC captures morning news cycle
    - Manual trigger with optional season/week for ad-hoc runs
    - Auto-opens GitHub issue on failure (matches weekly-pipeline pattern)
    - No AWS credentials needed (local data only for now)
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && cat .github/workflows/daily-sentiment.yml | python -c "import sys, yaml; yaml.safe_load(sys.stdin); print('YAML valid')"</automated>
  </verify>
  <done>
    - GitHub Actions workflow file is valid YAML
    - Cron schedule is daily at noon UTC
    - Manual dispatch supported with optional season/week inputs
    - Failure auto-opens GitHub issue
    - ANTHROPIC_API_KEY is optional (rule-based fallback works)
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GHA -> Scripts | GitHub Actions environment runs pipeline scripts |
| External APIs | Reddit, RSS feeds fetched during cron |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-SV2-09 | Spoofing | GHA secrets | mitigate | ANTHROPIC_API_KEY stored in GitHub Secrets, not in code |
| T-SV2-10 | DoS | Daily cron | accept | Single daily run, <5 min execution, well within GHA limits |
</threat_model>

<verification>
1. Dry run works: `python scripts/daily_sentiment_pipeline.py --dry-run --verbose`
2. Full run works: `python scripts/daily_sentiment_pipeline.py --season 2025 --week 1 --verbose`
3. GHA YAML is valid: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily-sentiment.yml'))"`
4. Re-run is idempotent: running twice produces no duplicate signals
</verification>

<success_criteria>
- Daily pipeline script runs all 3 ingestion sources + extraction + aggregation
- GitHub Actions cron fires daily at noon UTC
- Pipeline is idempotent (safe to re-run)
- Failure opens a GitHub issue automatically
</success_criteria>

<output>
After completion, create `.planning/phases/sentiment-v2/SV2-04-SUMMARY.md`
</output>
