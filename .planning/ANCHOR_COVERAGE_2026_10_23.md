# Anchor "coverage erosion" was not a defect (2026-10-23)

`MODEL_ASSESSMENT_2026_10_21.md` finding 5 recorded that the shipped Sleeper
anchor matched a falling share of eligible WR/RB/TE rows — 93% in week 3 down
to 79% by week 6 — and called it "a load-bearing lever quietly stopped firing
on one row in five". **That framing was wrong.** Diagnosed here, with the fix
being to the measurement rather than to the anchor.

## What the numbers actually show

Per-position match rates, 2026 w3-7, against the published boards:

| wk | pos | ours | Sleeper rows | matched | raw cov | unmatched >=5pt |
|---|---|---|---|---|---|---|
| 3 | WR | 152 | 163 | 142 | 93% | 1 |
| 3 | RB | 95 | 103 | 91 | 96% | 1 |
| 3 | TE | 73 | 103 | 66 | 90% | 1 |
| 4 | WR | 154 | 158 | 136 | 88% | 1 |
| 5 | TE | 82 | 100 | 67 | 82% | 0 |
| 6 | WR | 158 | **135** | 122 | 77% | 2 |
| 6 | RB | 93 | **83** | 71 | 76% | 1 |
| 7 | WR | 161 | 140 | 127 | 79% | 3 |

Sleeper's published skill-position slate shrinks through the season while our
board does not:

```
wk3 401 rows -> wk4 386 -> wk5 372 -> wk6 337 -> wk7 360
```

Our board holds ~330-340 eligible WR/RB/TE rows throughout. So raw coverage
falls because the *supply* shrank, not because our matching broke.

**The unmatched rows are almost entirely deep bench.** Across five weeks only
**15 unmatched rows were projected >= 5 pts** — about 3 per week out of ~340,
mean projection 7.56. Coverage over the rows that can actually change a
lineup held at roughly **99%**.

## The notable misses are absent from Sleeper, not mis-joined

The unmatched startables include real players — T.Etienne 11.27, D.Achane
11.03, D.Adams 8.80, T.Thornton 10.04, D.Moore 8.24, J.Gibbs 6.59 — so this
was worth checking properly rather than waving through. For each one, searched
Sleeper's Bronze snapshot for that week by id *and* by surname:

```
wk4 RB T.Etienne  our_id=00-0036973  in sleeper by id: 0  by surname: ABSENT
wk4 RB D.Achane   our_id=00-0039040  in sleeper by id: 0  by surname: ABSENT
wk6 RB J.Gibbs    our_id=00-0039139  in sleeper by id: 0  by surname: ABSENT
wk6 WR D.Moore    our_id=00-0034827  in sleeper by id: 0  by surname: ABSENT
wk7 WR D.Adams    our_id=00-0031381  in sleeper by id: 0  by surname: ABSENT
wk7 WR D.Samuel   our_id=00-0035719  in sleeper by id: 0  by surname: ABSENT
```

Every one is **genuinely missing from Sleeper's feed** for that week. The
Bronze carries GSIS ids exactly as our board does, so there is **no
id-mapping failure** — the 2026 w1-3 crosswalk bug (see
`SEASON_2026_WEEKS_1_2_RETRO.md`) is fixed and stayed fixed. The pattern
across all six is that they were injured or inactive that week, which Sleeper
appears to omit from its projections.

Nothing on our side can recover a player the source did not publish.

## The actual defect: the guard measured the wrong denominator

The existing guard warns when matched < 50% of **all** rows at a position.
That threshold is simultaneously too lax and measuring the wrong thing:

- It cannot distinguish "Sleeper dropped 60 bench players" (harmless, and the
  normal seasonal pattern) from "our join broke for 60 starters" (critical).
- At 76-79% raw coverage it stays silent, so a real partial regression could
  sit undetected until it crossed 50%.

**Fixed:** `build_sleeper_lookup` now also reports `n_startable_pos_rows` and
`n_startable_matched` — the same pair restricted to rows projected
>= `STARTABLE_PTS` (5.0, matching `consensus_metrics.CONSENSUS_MIN_PTS`) — and
`generate_projections.py` logs startable coverage per position and warns below
`STARTABLE_COVERAGE_MIN` (0.90). The old 50%-of-all-rows floor stays as a
backstop for total failure.

Live week-7 run after the fix:

```
Sleeper consensus anchor (WR): startable coverage 65/66 (98%)
Sleeper consensus anchor (RB): startable coverage 42/42 (100%)
Sleeper consensus anchor (TE): startable coverage 19/19 (100%)
Sleeper consensus anchor (QB): startable coverage 29/31 (94%)
```

Which is the honest picture: the anchor is healthy, and had been all along.

## Lesson

This is the third claim from the 2026-10-21 assessment to need correcting on
closer measurement, after the QB anchor's magnitude and the TE weight sweep.
The common thread is asserting from an aggregate before checking what it is
made of — 79% coverage sounds like a lever half-broken, and it was a lever
working fine on everything that mattered. A coverage metric needs a
denominator chosen to match the decision it informs.
