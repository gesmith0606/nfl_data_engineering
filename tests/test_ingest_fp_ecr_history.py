"""Tests for scripts/ingest_fp_ecr_history.py — DynastyProcess FP-ECR archive ingestion.

No live network access: fetch_fp_ecr_csv/fetch_playerid_crosswalk aren't exercised
against the network here. Fixtures mirror the real archive's columns/values
(scout-verified 2026-08-18: db_fpecr.csv.gz page_type/fp_page/id columns,
db_playerids.csv fantasypros_id/gsis_id/sleeper_id columns) without depending
on the ephemeral scratchpad download path.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import ingest_fp_ecr_history as fpecr  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_schedule_cache():
    """The module-level schedule window cache must not leak between tests."""
    fpecr._SCHEDULE_CACHE.clear()
    yield
    fpecr._SCHEDULE_CACHE.clear()


def _raw_row(page_type, fp_page, player, fp_id, pos, team, ecr, scrape_date, sd=0.5, best=1, worst=3):
    return {
        "fp_page": fp_page,
        "page_type": page_type,
        "player": player,
        "id": fp_id,
        "pos": pos,
        "team": team,
        "ecr": ecr,
        "sd": sd,
        "best": best,
        "worst": worst,
        "mergename": player.lower().replace(" ", ""),
        "tm": team,
        "scrape_date": scrape_date,
    }


class TestFilterWeeklyRows:
    def test_keeps_only_weekly_position_pages(self):
        df = pd.DataFrame(
            [
                _raw_row("weekly-wr", "/nfl/rankings/ppr-wr.php", "Tyreek Hill", 15802, "WR", "MIA", 1.4, "2023-10-06"),
                _raw_row("dynasty-wr", "/nfl/rankings/dynasty-wr.php", "Tyreek Hill", 15802, "WR", "MIA", 3.0, "2023-10-06"),
                _raw_row("weekly-op", "/nfl/rankings/ppr-superflex.php", "Tyreek Hill", 15802, "WR", "MIA", 8.0, "2023-10-06"),
                _raw_row("weekly-qb", "/nfl/rankings/qb.php", "Josh Allen", 15801, "QB", "BUF", 1.0, "2023-10-06"),
            ]
        )
        out = fpecr.filter_weekly_rows(df)
        assert set(out["page_type"]) == {"weekly-wr", "weekly-qb"}
        assert len(out) == 2


class TestScoringFromFpPage:
    @pytest.mark.parametrize(
        "fp_page,expected",
        [
            ("/nfl/rankings/ppr-wr.php", "ppr"),
            ("/nfl/rankings/ppr-rb.php", "ppr"),
            ("/nfl/rankings/ppr-te.php", "ppr"),
            ("/nfl/rankings/qb.php", "standard"),
            ("/nfl/rankings/half-ppr-wr.php", "half_ppr"),
            ("/nfl/rankings/wr.php", "standard"),
        ],
    )
    def test_scoring_derivation(self, fp_page, expected):
        assert fpecr.scoring_from_fp_page(fp_page) == expected


class TestDeriveSeason:
    def test_mid_season_date_same_year(self):
        assert fpecr.derive_season(date(2023, 10, 6)) == 2023

    def test_january_date_belongs_to_prior_season(self):
        assert fpecr.derive_season(date(2024, 1, 10)) == 2023

    def test_march_date_is_new_season(self):
        assert fpecr.derive_season(date(2024, 3, 1)) == 2024


class TestMapScrapeDateToWeek:
    """windows mirror real 2023 Bronze schedules REG gamedays (verified 2026-08-18):
    week4 2023-09-28..2023-10-02, week5 2023-10-05..2023-10-09,
    week18 2024-01-06..2024-01-07 (season=2023, per NFL convention).
    """

    WINDOWS_2023 = {
        4: (date(2023, 9, 28), date(2023, 10, 2)),
        5: (date(2023, 10, 5), date(2023, 10, 9)),
        18: (date(2024, 1, 6), date(2024, 1, 7)),
    }

    def test_friday_scrape_within_week_window_maps_to_that_week(self):
        # Friday 2023-10-06: after week5's Thursday game, before Sun/Mon games.
        assert fpecr.map_scrape_date_to_week(date(2023, 10, 6), self.WINDOWS_2023) == 5

    def test_scrape_between_weeks_maps_to_upcoming_week(self):
        # Tuesday 2023-10-03: week4 already concluded (max 10-02), week5 hasn't
        # started (min 10-05) -> maps to the upcoming week, not the past one.
        assert fpecr.map_scrape_date_to_week(date(2023, 10, 3), self.WINDOWS_2023) == 5

    def test_january_playoff_adjacent_within_week18_maps_to_week18(self):
        assert fpecr.map_scrape_date_to_week(date(2024, 1, 5), self.WINDOWS_2023) == 18

    def test_january_date_past_week18_is_unmapped(self):
        # After week 18 concludes (wild-card weekend+) -> archive doesn't cover
        # playoff-week rankings under weekly-position pages; must not silently
        # assign a week.
        assert fpecr.map_scrape_date_to_week(date(2024, 1, 10), self.WINDOWS_2023) is None

    def test_empty_windows_returns_none(self):
        assert fpecr.map_scrape_date_to_week(date(2023, 10, 6), {}) is None


class TestAddSeasonWeekScoring:
    def test_maps_and_drops_unmapped_rows(self):
        fpecr._SCHEDULE_CACHE[2023] = {
            5: (date(2023, 10, 5), date(2023, 10, 9)),
            18: (date(2024, 1, 6), date(2024, 1, 7)),
        }
        df = pd.DataFrame(
            [
                _raw_row("weekly-wr", "/nfl/rankings/ppr-wr.php", "Tyreek Hill", 15802, "WR", "MIA", 1.4, "2023-10-06"),
                # Past week 18's window -> should be dropped (no week mapping).
                _raw_row("weekly-wr", "/nfl/rankings/ppr-wr.php", "Tyreek Hill", 15802, "WR", "MIA", 1.2, "2024-01-10"),
            ]
        )
        out = fpecr.add_season_week_scoring(df)
        assert len(out) == 1
        assert out.iloc[0]["season"] == 2023
        assert out.iloc[0]["week"] == 5
        assert out.iloc[0]["scoring"] == "ppr"


class TestJoinCrosswalk:
    def test_matched_and_unmatched_ids(self):
        df = pd.DataFrame(
            {
                "id": [15802, 19236, 99999999],  # last id has no crosswalk row
                "player_name": ["Tyreek Hill", "Justin Jefferson", "Nobody"],
            }
        )
        crosswalk = pd.DataFrame(
            {
                "fantasypros_id": [15802.0, 19236.0, 13981.0],
                "gsis_id": ["00-0033040", "00-0036322", "00-0031588"],
                "sleeper_id": [3321.0, 6794.0, 2449.0],
                "name": ["Tyreek Hill", "Justin Jefferson", "Stefon Diggs"],
            }
        )
        out = fpecr.join_crosswalk(df, crosswalk)
        assert out.loc[out["player_name"] == "Tyreek Hill", "gsis_id"].iloc[0] == "00-0033040"
        assert out.loc[out["player_name"] == "Justin Jefferson", "gsis_id"].iloc[0] == "00-0036322"
        assert pd.isna(out.loc[out["player_name"] == "Nobody", "gsis_id"].iloc[0])
        # 2/3 rows joined
        assert out["gsis_id"].notna().mean() == pytest.approx(2 / 3)


class TestDerivePosRank:
    def test_rank_ascending_with_ties(self):
        df = pd.DataFrame(
            {
                "season": [2023] * 4,
                "week": [5] * 4,
                "scoring": ["ppr"] * 4,
                "position": ["WR"] * 4,
                "ecr": [1.4, 1.4, 3.6, 4.0],
            }
        )
        out = fpecr.derive_pos_rank(df)
        # Tied ecr values (1.4, 1.4) both get the min rank (1); next distinct
        # value jumps to 3, matching standard "min" tie-break ranking.
        assert out["pos_rank"].tolist() == [1, 1, 3, 4]

    def test_groups_are_independent_per_season_week_scoring_position(self):
        df = pd.DataFrame(
            {
                "season": [2023, 2023, 2024, 2024],
                "week": [5, 5, 5, 5],
                "scoring": ["ppr"] * 4,
                "position": ["WR", "RB", "WR", "WR"],
                "ecr": [1.4, 1.0, 2.0, 5.0],
            }
        )
        out = fpecr.derive_pos_rank(df)
        # Each (season, week, scoring, position) group ranks independently,
        # so the RB row and the 2023 WR row both get pos_rank 1.
        assert out.loc[(out.position == "RB"), "pos_rank"].iloc[0] == 1
        assert out.loc[(out.season == 2023) & (out.position == "WR"), "pos_rank"].iloc[0] == 1
        assert out.loc[(out.season == 2024) & (out.ecr == 2.0), "pos_rank"].iloc[0] == 1
        assert out.loc[(out.season == 2024) & (out.ecr == 5.0), "pos_rank"].iloc[0] == 2


class TestValidateFailLoud:
    def test_raises_on_zero_rows_for_a_required_season(self):
        df = pd.DataFrame({"season": [2020, 2021, 2022, 2023]})  # 2024 missing
        with pytest.raises(RuntimeError, match="ZERO rows for season 2024"):
            fpecr.validate_fail_loud(df, [2020, 2021, 2022, 2023, 2024])

    def test_passes_when_all_seasons_present(self):
        df = pd.DataFrame({"season": [2020, 2021, 2022, 2023, 2024]})
        fpecr.validate_fail_loud(df, [2020, 2021, 2022, 2023, 2024])  # no raise


class TestBuildBronzeSilverIntegration:
    def test_end_to_end_small_fixture(self):
        fpecr._SCHEDULE_CACHE[2023] = {
            5: (date(2023, 10, 5), date(2023, 10, 9)),
        }
        raw = pd.DataFrame(
            [
                _raw_row("weekly-wr", "/nfl/rankings/ppr-wr.php", "Tyreek Hill", 15802, "WR", "MIA", 1.4, "2023-10-06"),
                _raw_row("weekly-wr", "/nfl/rankings/ppr-wr.php", "Justin Jefferson", 19236, "WR", "MIN", 1.6, "2023-10-06"),
                _raw_row("dynasty-wr", "/nfl/rankings/dynasty-wr.php", "Tyreek Hill", 15802, "WR", "MIA", 3.0, "2023-10-06"),
            ]
        )
        crosswalk = pd.DataFrame(
            {
                "fantasypros_id": [15802.0, 19236.0],
                "gsis_id": ["00-0033040", "00-0036322"],
                "sleeper_id": [3321.0, 6794.0],
            }
        )
        bronze = fpecr.build_bronze(raw)
        assert len(bronze) == 2  # dynasty-wr row excluded
        assert set(bronze.columns) >= set(fpecr.BRONZE_RAW_COLS) | {"season", "week", "scoring"}

        silver = fpecr.build_silver(bronze, crosswalk)
        assert list(silver.columns) == fpecr.SILVER_COLUMNS
        assert silver["gsis_id"].notna().all()
        top = silver.sort_values("ecr").iloc[0]
        assert top["player_name"] == "Tyreek Hill"
        assert top["pos_rank"] == 1


class TestWriteParquet:
    def test_writes_one_file_per_season_partition(self, tmp_path):
        df = pd.DataFrame({"season": [2023, 2023, 2024], "value": [1, 2, 3]})
        written = fpecr.write_parquet(df, str(tmp_path), "fp_ecr", [2023, 2024, 2025])
        assert len(written) == 2  # 2025 has no rows -> skipped
        assert (tmp_path / "season=2023" / "fp_ecr_2023.parquet").exists()
        assert (tmp_path / "season=2024" / "fp_ecr_2024.parquet").exists()
        assert not (tmp_path / "season=2025").exists()
