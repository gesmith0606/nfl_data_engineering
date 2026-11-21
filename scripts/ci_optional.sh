#!/usr/bin/env bash
# Run an OPTIONAL enrichment step: on failure, degrade loudly but never fail.
#
# Usage: scripts/ci_optional.sh "<label>" "<impact>" <command> [args...]
#
# This is the single place that defines "optional" for weekly-pipeline.yml.
#   REQUIRED (a failure must fail the run, so no wrapper): player_weekly,
#     snap_counts, Silver player transformation, projection generation, the
#     sanity gate, the Gold commit.
#   OPTIONAL (wrap with this script): injuries, rosters, ngs, pfr_weekly, qbr,
#     pbp+participation. The models tolerate their features as NaN (QBR 2024+
#     is permanently absent upstream in nflverse).
# A failure emits a ::warning:: and a line in the run summary.
set -u
label="$1"; impact="$2"; shift 2
"$@"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "::warning::${label} failed (exit ${rc}) — ${impact}"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "- :warning: optional input **${label}** failed (exit ${rc}): ${impact}" >> "$GITHUB_STEP_SUMMARY"
  fi
fi
exit 0
