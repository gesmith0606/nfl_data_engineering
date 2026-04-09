"""
Sentiment pipeline package.

Processes unstructured news text (RSS, Sleeper, Twitter, Reddit, official
injury reports) into structured per-player-week sentiment signals that feed
into the projection engine as a final adjustment multiplier.

Package layout follows the architecture described in
.planning/unstructured-data/ARCHITECTURE.md:

  ingestion/   — source-specific ingestors (RSS, Sleeper, Twitter, …)
  processing/  — Claude-powered entity extraction + sentiment scoring
  aggregation/ — Silver → Gold aggregation and multiplier calculation
  storage/     — S3 and Supabase persistence helpers
  alerts/      — Downstream alert dispatch (injury cascade, notifications)
"""
