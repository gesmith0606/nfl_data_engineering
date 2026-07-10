"""Tests for the vacated opportunity network (UC1)."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_vacated_opportunity import (
    VACATED_FEATURE_COLUMNS,
    build_vacated_opportunity_data,
    compute_season_usage_shares,
    compute_vacated_opportunity_features,
    identify_departures_arrivals,
    normalize_depth_chart,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def prior_weekly():
    """Season N-1 weekly usage: KC has a departing WR1, SF is stable."""
    rows = []
    # KC: WR1 (departing) 40 targets, WR2 30, TE1 20, RB1 10 targets / 80 carries,
    # RB2 20 carries over 2 weeks.
    for week in (1, 2):
        rows += [
            dict(
                player_id="WR1_KC",
                recent_team="KC",
                position="WR",
                week=week,
                targets=20,
                carries=0,
            ),
            dict(
                player_id="WR2_KC",
                recent_team="KC",
                position="WR",
                week=week,
                targets=15,
                carries=0,
            ),
            dict(
                player_id="TE1_KC",
                recent_team="KC",
                position="TE",
                week=week,
                targets=10,
                carries=0,
            ),
            dict(
                player_id="RB1_KC",
                recent_team="KC",
                position="RB",
                week=week,
                targets=5,
                carries=40,
            ),
            dict(
                player_id="RB2_KC",
                recent_team="KC",
                position="RB",
                week=week,
                targets=0,
                carries=10,
            ),
            dict(
                player_id="WR1_SF",
                recent_team="SF",
                position="WR",
                week=week,
                targets=25,
                carries=0,
            ),
            dict(
                player_id="RB1_SF",
                recent_team="SF",
                position="RB",
                week=week,
                targets=5,
                carries=50,
            ),
        ]
    return pd.DataFrame(rows)


@pytest.fixture
def current_roster():
    """Season N roster: WR1_KC left KC (signed with SF); rookie WR drafted by KC."""
    return pd.DataFrame(
        [
            dict(player_id="WR2_KC", team="KC", position="WR"),
            dict(player_id="WR_ROOKIE", team="KC", position="WR"),
            dict(player_id="TE1_KC", team="KC", position="TE"),
            dict(player_id="RB1_KC", team="KC", position="RB"),
            dict(player_id="RB2_KC", team="KC", position="RB"),
            dict(player_id="WR1_SF", team="SF", position="WR"),
            dict(player_id="WR1_KC", team="SF", position="WR"),  # arrival to SF
            dict(player_id="RB1_SF", team="SF", position="RB"),
        ]
    )


@pytest.fixture
def depth_chart_old_schema():
    """Pre-2025 depth chart schema for season N."""
    return pd.DataFrame(
        [
            dict(
                club_code="KC",
                gsis_id="WR2_KC",
                position="WR",
                depth_team="1",
                week=1,
                season=2024,
                formation="Offense",
            ),
            dict(
                club_code="KC",
                gsis_id="WR_ROOKIE",
                position="WR",
                depth_team="2",
                week=1,
                season=2024,
                formation="Offense",
            ),
            dict(
                club_code="KC",
                gsis_id="TE1_KC",
                position="TE",
                depth_team="1",
                week=1,
                season=2024,
                formation="Offense",
            ),
            dict(
                club_code="KC",
                gsis_id="RB1_KC",
                position="RB",
                depth_team="1",
                week=1,
                season=2024,
                formation="Offense",
            ),
            dict(
                club_code="KC",
                gsis_id="RB2_KC",
                position="RB",
                depth_team="2",
                week=1,
                season=2024,
                formation="Offense",
            ),
            dict(
                club_code="SF",
                gsis_id="WR1_SF",
                position="WR",
                depth_team="1",
                week=1,
                season=2024,
                formation="Offense",
            ),
            dict(
                club_code="SF",
                gsis_id="WR1_KC",
                position="WR",
                depth_team="2",
                week=1,
                season=2024,
                formation="Offense",
            ),
            dict(
                club_code="SF",
                gsis_id="RB1_SF",
                position="RB",
                depth_team="1",
                week=1,
                season=2024,
                formation="Offense",
            ),
            # Later-week row that must be ignored (earliest snapshot wins)
            dict(
                club_code="KC",
                gsis_id="WR2_KC",
                position="WR",
                depth_team="3",
                week=5,
                season=2024,
                formation="Offense",
            ),
        ]
    )


@pytest.fixture
def draft_picks():
    return pd.DataFrame(
        [dict(gsis_id="WR_ROOKIE", round=1, pick=10, position="WR", team="KC")]
    )


# ---------------------------------------------------------------------------
# compute_season_usage_shares
# ---------------------------------------------------------------------------


class TestSeasonUsageShares:
    def test_totals_based_shares(self, prior_weekly):
        shares = compute_season_usage_shares(prior_weekly)
        kc_wr1 = shares[shares["player_id"] == "WR1_KC"].iloc[0]
        # KC targets: 40+30+20+10 = 100 per 2 weeks; WR1 has 40
        assert kc_wr1["target_share"] == pytest.approx(0.40)
        rb1 = shares[shares["player_id"] == "RB1_KC"].iloc[0]
        assert rb1["carry_share"] == pytest.approx(80 / 100)

    def test_playoff_weeks_excluded(self, prior_weekly):
        playoff = prior_weekly.copy()
        playoff.loc[len(playoff)] = dict(
            player_id="WR9_KC",
            recent_team="KC",
            position="WR",
            week=19,
            targets=50,
            carries=0,
        )
        shares = compute_season_usage_shares(playoff)
        assert "WR9_KC" not in set(shares["player_id"])

    def test_empty_input(self):
        assert compute_season_usage_shares(pd.DataFrame()).empty

    def test_missing_carries_column(self, prior_weekly):
        no_carries = prior_weekly.drop(columns=["carries"])
        shares = compute_season_usage_shares(no_carries)
        assert (shares["carry_share"] == 0.0).all()


# ---------------------------------------------------------------------------
# normalize_depth_chart
# ---------------------------------------------------------------------------


class TestNormalizeDepthChart:
    def test_old_schema(self, depth_chart_old_schema):
        dc = normalize_depth_chart(depth_chart_old_schema)
        assert set(dc.columns) == {"team", "player_id", "position", "pos_rank"}
        wr2 = dc[dc["player_id"] == "WR2_KC"].iloc[0]
        assert wr2["pos_rank"] == 1  # earliest week wins over week-5 rank 3

    def test_new_schema(self):
        new = pd.DataFrame(
            [
                dict(
                    team="KC",
                    gsis_id="WR2_KC",
                    pos_abb="WR",
                    pos_rank=1,
                    dt="2025-08-01",
                ),
                dict(
                    team="KC",
                    gsis_id="WR2_KC",
                    pos_abb="WR",
                    pos_rank=2,
                    dt="2025-10-01",
                ),  # later snapshot ignored
                dict(
                    team="KC",
                    gsis_id="RB1_KC",
                    pos_abb="RB",
                    pos_rank=1,
                    dt="2025-08-01",
                ),
            ]
        )
        dc = normalize_depth_chart(new)
        assert len(dc) == 2
        assert dc[dc["player_id"] == "WR2_KC"].iloc[0]["pos_rank"] == 1

    def test_empty_input(self):
        assert normalize_depth_chart(pd.DataFrame()).empty

    def test_non_fantasy_positions_dropped(self, depth_chart_old_schema):
        with_ol = pd.concat(
            [
                depth_chart_old_schema,
                pd.DataFrame(
                    [
                        dict(
                            club_code="KC",
                            gsis_id="C1_KC",
                            position="C",
                            depth_team="1",
                            week=1,
                            season=2024,
                            formation="Offense",
                        )
                    ]
                ),
            ],
            ignore_index=True,
        )
        dc = normalize_depth_chart(with_ol)
        assert "C1_KC" not in set(dc["player_id"])


# ---------------------------------------------------------------------------
# identify_departures_arrivals
# ---------------------------------------------------------------------------


class TestDeparturesArrivals:
    def test_departure_detected(self, prior_weekly, current_roster):
        usage = compute_season_usage_shares(prior_weekly)
        departures, _ = identify_departures_arrivals(usage, current_roster)
        dep_ids = set(zip(departures["player_id"], departures["team"]))
        assert ("WR1_KC", "KC") in dep_ids  # left KC
        assert ("WR2_KC", "KC") not in dep_ids  # still on KC

    def test_arrival_detected_with_prior_shares(self, prior_weekly, current_roster):
        usage = compute_season_usage_shares(prior_weekly)
        _, arrivals = identify_departures_arrivals(usage, current_roster)
        arr = arrivals[arrivals["player_id"] == "WR1_KC"]
        assert len(arr) == 1
        assert arr.iloc[0]["team"] == "SF"
        assert arr.iloc[0]["prior_team"] == "KC"
        assert arr.iloc[0]["target_share"] == pytest.approx(0.40)

    def test_rookie_not_departure_or_arrival(self, prior_weekly, current_roster):
        usage = compute_season_usage_shares(prior_weekly)
        departures, arrivals = identify_departures_arrivals(usage, current_roster)
        assert "WR_ROOKIE" not in set(departures["player_id"])
        assert "WR_ROOKIE" not in set(arrivals["player_id"])

    def test_empty_inputs(self):
        dep, arr = identify_departures_arrivals(pd.DataFrame(), pd.DataFrame())
        assert dep.empty and arr.empty


# ---------------------------------------------------------------------------
# compute_vacated_opportunity_features
# ---------------------------------------------------------------------------


class TestVacatedOpportunityFeatures:
    def _features(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        return compute_vacated_opportunity_features(
            prior_weekly_df=prior_weekly,
            current_roster_df=current_roster,
            season=2024,
            depth_charts_df=depth_chart_old_schema,
            draft_picks_df=draft_picks,
        )

    def test_output_schema(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        for col in VACATED_FEATURE_COLUMNS:
            assert col in feats.columns
        assert (feats["season"] == 2024).all()

    def test_kc_vacancy_from_departed_wr1(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        kc = feats[feats["team"] == "KC"]
        # WR1_KC vacated 40% of KC targets; no arrivals to KC -> net = gross
        assert np.allclose(kc["vacated_target_share_abs"], 0.40)
        assert np.allclose(kc["net_target_vacancy"], 0.40)

    def test_absorption_ordered_by_depth_rank(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        kc = feats[feats["team"] == "KC"].set_index("player_id")
        # WR2 (rank 1) absorbs more than the rookie (rank 2); both positive.
        assert (
            kc.loc["WR2_KC", "vacancy_absorbed_share"]
            > kc.loc["WR_ROOKIE", "vacancy_absorbed_share"]
            > 0.0
        )

    def test_absorbed_share_bounded_by_vacancy(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        for team, grp in feats.groupby("team"):
            total_vacancy = (
                grp["net_target_vacancy"].iloc[0] + grp["net_carry_vacancy"].iloc[0]
            )
            assert grp["vacancy_absorbed_share"].sum() <= total_vacancy + 1e-6

    def test_sf_net_vacancy_reduced_by_arrival(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        sf = feats[feats["team"] == "SF"]
        # SF lost nobody but gained WR1_KC (0.40 import) -> net target vacancy 0
        assert np.allclose(sf["net_target_vacancy"], 0.0)

    def test_arrival_displacement(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        arr = feats[feats["player_id"] == "WR1_KC"].iloc[0]
        assert arr["team"] == "SF"
        assert arr["arrival_displacement"] == pytest.approx(0.40)
        stay = feats[feats["player_id"] == "WR2_KC"].iloc[0]
        assert stay["arrival_displacement"] == 0.0

    def test_competition_counts(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        kc_wr2 = feats[feats["player_id"] == "WR2_KC"].iloc[0]
        # KC WRs with a claim: WR2 + rookie -> 1 competitor excluding self
        assert kc_wr2["vacancy_competition_n"] == 1

    def test_empty_inputs_return_empty_with_schema(self):
        feats = compute_vacated_opportunity_features(
            prior_weekly_df=pd.DataFrame(),
            current_roster_df=pd.DataFrame(),
            season=2024,
        )
        assert feats.empty
        for col in VACATED_FEATURE_COLUMNS:
            assert col in feats.columns

    def test_no_depth_chart_falls_back_to_prior_share(
        self, prior_weekly, current_roster
    ):
        feats = compute_vacated_opportunity_features(
            prior_weekly_df=prior_weekly,
            current_roster_df=current_roster,
            season=2024,
        )
        kc_wr2 = feats[feats["player_id"] == "WR2_KC"].iloc[0]
        # WR2 had 30% prior target share (> MIN_SHARE_COMPETITOR) so still absorbs
        assert kc_wr2["vacancy_absorbed_share"] > 0.0

    def test_features_non_negative(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = self._features(
            prior_weekly, current_roster, depth_chart_old_schema, draft_picks
        )
        for col in VACATED_FEATURE_COLUMNS:
            assert (feats[col] >= 0).all(), f"{col} has negative values"


# ---------------------------------------------------------------------------
# Position scoping + noise threshold (post-review hardening)
# ---------------------------------------------------------------------------


class TestVacancyPoolScoping:
    def test_qb_departure_does_not_create_target_vacancy(self):
        """A departing QB's scramble targets must not inflate the WR pool."""
        weekly = pd.DataFrame(
            [
                dict(
                    player_id="QB1",
                    recent_team="KC",
                    position="QB",
                    week=1,
                    targets=5,
                    carries=30,
                ),
                dict(
                    player_id="WR1",
                    recent_team="KC",
                    position="WR",
                    week=1,
                    targets=45,
                    carries=0,
                ),
            ]
        )
        roster = pd.DataFrame(
            [dict(player_id="WR1", team="KC", position="WR")]  # QB1 departed
        )
        feats = compute_vacated_opportunity_features(
            prior_weekly_df=weekly, current_roster_df=roster, season=2024
        )
        kc = feats[feats["team"] == "KC"].iloc[0]
        assert kc["vacated_target_share_abs"] == pytest.approx(0.0)
        # QB carries also excluded from the RB carry pool
        assert kc["vacated_carry_share_abs"] == pytest.approx(0.0)

    def test_wr_carry_departure_not_in_rb_pool(self):
        """WR jet-sweep carries must not create RB carry vacancy."""
        weekly = pd.DataFrame(
            [
                dict(
                    player_id="WR1",
                    recent_team="KC",
                    position="WR",
                    week=1,
                    targets=40,
                    carries=8,
                ),
                dict(
                    player_id="RB1",
                    recent_team="KC",
                    position="RB",
                    week=1,
                    targets=10,
                    carries=72,
                ),
            ]
        )
        roster = pd.DataFrame(
            [dict(player_id="RB1", team="KC", position="RB")]  # WR1 departed
        )
        feats = compute_vacated_opportunity_features(
            prior_weekly_df=weekly, current_roster_df=roster, season=2024
        )
        kc = feats[feats["team"] == "KC"].iloc[0]
        # WR1's 80% target share vacates; his 10% carry share does not
        assert kc["vacated_target_share_abs"] == pytest.approx(0.80)
        assert kc["vacated_carry_share_abs"] == pytest.approx(0.0)

    def test_subthreshold_departures_ignored(self):
        """Practice-squad churn (sub-2% shares) must not sum into vacancy."""
        rows = [
            dict(
                player_id="WR_STAR",
                recent_team="KC",
                position="WR",
                week=1,
                targets=90,
                carries=0,
            )
        ]
        # 10 fringe WRs at 1 target each (1% share) all departing
        for i in range(10):
            rows.append(
                dict(
                    player_id=f"WR_FRINGE{i}",
                    recent_team="KC",
                    position="WR",
                    week=1,
                    targets=1,
                    carries=0,
                )
            )
        weekly = pd.DataFrame(rows)
        roster = pd.DataFrame([dict(player_id="WR_STAR", team="KC", position="WR")])
        feats = compute_vacated_opportunity_features(
            prior_weekly_df=weekly, current_roster_df=roster, season=2024
        )
        kc = feats[feats["team"] == "KC"].iloc[0]
        assert kc["vacated_target_share_abs"] == pytest.approx(0.0)

    def test_absorbed_share_capped_at_one(
        self, prior_weekly, current_roster, depth_chart_old_schema, draft_picks
    ):
        feats = compute_vacated_opportunity_features(
            prior_weekly_df=prior_weekly,
            current_roster_df=current_roster,
            season=2024,
            depth_charts_df=depth_chart_old_schema,
            draft_picks_df=draft_picks,
        )
        assert (feats["vacancy_absorbed_share"] <= 1.0).all()
        assert (feats["net_target_vacancy"] <= 1.0).all()
        assert (feats["net_carry_vacancy"] <= 1.0).all()


# ---------------------------------------------------------------------------
# Preseason engine integration
# ---------------------------------------------------------------------------


class TestPreseasonEngineIntegration:
    def _seasonal_df(self):
        rows = []
        for pid, team in (("WR_A", "KC"), ("WR_B", "SF")):
            for season in (2024, 2025):
                rows.append(
                    dict(
                        player_id=pid,
                        season=season,
                        player_name=f"Player {pid}",
                        position="WR",
                        recent_team=team,
                        games=17,
                        targets=120,
                        receptions=80,
                        receiving_yards=1000,
                        receiving_tds=6,
                        carries=0,
                        rushing_yards=0,
                        rushing_tds=0,
                        passing_yards=0,
                        passing_tds=0,
                        interceptions=0,
                    )
                )
        return pd.DataFrame(rows)

    def test_boost_applied_and_bounded(self):
        from projection_engine import (
            VACATED_OPPORTUNITY_BETA,
            generate_preseason_projections,
        )

        seasonal = self._seasonal_df()
        vac = pd.DataFrame([dict(player_id="WR_A", vacancy_absorbed_share=0.20)])

        base = generate_preseason_projections(seasonal, target_season=2026)
        boosted = generate_preseason_projections(
            seasonal, target_season=2026, vacated_features_df=vac
        )

        def pts(df, pid):
            return df[df["player_id"] == pid]["projected_season_points"].iloc[0]

        expected_mult = 1.0 + VACATED_OPPORTUNITY_BETA * 0.20
        assert pts(boosted, "WR_A") == pytest.approx(
            pts(base, "WR_A") * expected_mult, rel=0.01
        )
        # Player without vacancy features is untouched
        assert pts(boosted, "WR_B") == pytest.approx(pts(base, "WR_B"), rel=1e-6)
        # Invariant: no negative projections
        assert (boosted["projected_season_points"] >= 0).all()

    def test_missing_feature_columns_skipped(self):
        from projection_engine import generate_preseason_projections

        seasonal = self._seasonal_df()
        bad = pd.DataFrame([dict(player_id="WR_A", wrong_col=0.5)])
        base = generate_preseason_projections(seasonal, target_season=2026)
        result = generate_preseason_projections(
            seasonal, target_season=2026, vacated_features_df=bad
        )
        a_base = base[base["player_id"] == "WR_A"]["projected_season_points"].iloc[0]
        a_res = result[result["player_id"] == "WR_A"]["projected_season_points"].iloc[0]
        assert a_res == pytest.approx(a_base, rel=1e-6)


# ---------------------------------------------------------------------------
# Integration smoke test on real local data
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRealDataSmoke:
    def test_build_2025_transition(self):
        feats = build_vacated_opportunity_data(2025)
        if feats.empty:
            pytest.skip("Local Bronze data for 2024/2025 not available")
        assert feats["team"].nunique() >= 30
        assert (feats["vacancy_absorbed_share"] >= 0).all()
        # Some teams must have lost meaningful target share
        assert feats["vacated_target_share_abs"].max() > 0.10
