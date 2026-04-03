# Phase 49: PBP Participation Data Ingestion - Context

**Gathered:** 2026-04-02
**Status:** Complete

<domain>
## Phase Boundary

Ingest PBP participation data (22 player IDs per snap — 11 offense, 11 defense) for all training seasons 2020-2025. This is the critical blocker for populating graph features: without knowing which players were on the field for each play, WR-CB co-occurrence, OL continuity, TE-LB coverage rate, and scheme matchup features cannot be computed.

Phase 46 identified that only 4/22 graph features had data because the standard PBP ingestion does not include participation columns. This phase resolves that by running `--include-participation` to capture `offense_players` and `defense_players` fields.

</domain>

<requirements>
## Requirements

- INGEST-01: PBP participation data ingested for seasons 2020-2025 with offense_players and defense_players columns stored in `data/bronze/pbp_participation/`
- INGEST-02: PBP participation data extended to 2016-2019 for full training history coverage
- INGEST-03: Participation ingestion is idempotent (re-runnable without duplicates)
</requirements>
