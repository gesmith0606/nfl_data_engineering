-- NFL Data Engineering -- PostgreSQL schema for the web platform.
--
-- Tables mirror the Pydantic models in web/api/models/schemas.py.
-- Designed for Supabase (PostgreSQL 15+) but works on any PostgreSQL 13+.

-- =========================================================================
-- Projections
-- =========================================================================
CREATE TABLE IF NOT EXISTS projections (
    id              SERIAL PRIMARY KEY,
    player_id       VARCHAR(20)    NOT NULL,
    player_name     VARCHAR(100)   NOT NULL,
    team            VARCHAR(5)     NOT NULL,
    position        VARCHAR(3)     NOT NULL,
    season          INTEGER        NOT NULL,
    week            INTEGER        NOT NULL,
    scoring_format  VARCHAR(10)    NOT NULL,
    projected_points DECIMAL(6,2)  NOT NULL,
    projected_floor  DECIMAL(6,2),
    projected_ceiling DECIMAL(6,2),
    proj_pass_yards  DECIMAL(7,2),
    proj_pass_tds    DECIMAL(5,2),
    proj_rush_yards  DECIMAL(7,2),
    proj_rush_tds    DECIMAL(5,2),
    proj_rec         DECIMAL(5,2),
    proj_rec_yards   DECIMAL(7,2),
    proj_rec_tds     DECIMAL(5,2),
    proj_fg_makes    DECIMAL(4,2),
    proj_xp_makes    DECIMAL(4,2),
    position_rank    INTEGER,
    injury_status    VARCHAR(20),
    generated_at     TIMESTAMP DEFAULT NOW(),
    UNIQUE(player_id, season, week, scoring_format)
);

-- =========================================================================
-- Game Predictions
-- =========================================================================
CREATE TABLE IF NOT EXISTS predictions (
    id               SERIAL PRIMARY KEY,
    game_id          VARCHAR(30)   NOT NULL,
    season           INTEGER       NOT NULL,
    week             INTEGER       NOT NULL,
    home_team        VARCHAR(5)    NOT NULL,
    away_team        VARCHAR(5)    NOT NULL,
    predicted_spread DECIMAL(5,2),
    predicted_total  DECIMAL(5,2),
    vegas_spread     DECIMAL(5,2),
    vegas_total      DECIMAL(5,2),
    spread_edge      DECIMAL(5,2),
    total_edge       DECIMAL(5,2),
    confidence_tier  VARCHAR(10),
    ats_pick         VARCHAR(10),
    ou_pick          VARCHAR(10),
    generated_at     TIMESTAMP DEFAULT NOW(),
    UNIQUE(game_id, season, week)
);

-- =========================================================================
-- College Player Stats
-- =========================================================================
CREATE TABLE IF NOT EXISTS college_player_stats (
    id              SERIAL PRIMARY KEY,
    player_name     VARCHAR(100)   NOT NULL,
    college_team    VARCHAR(50)    NOT NULL,
    conference      VARCHAR(20)    NOT NULL,
    position        VARCHAR(3)     NOT NULL,
    season          INTEGER        NOT NULL,
    passing_yards   DECIMAL(7,2),
    passing_tds     DECIMAL(5,2),
    rushing_yards   DECIMAL(7,2),
    rushing_tds     DECIMAL(5,2),
    receptions      DECIMAL(5,2),
    receiving_yards DECIMAL(7,2),
    receiving_tds   DECIMAL(5,2),
    games           INTEGER,
    conference_adjusted_yards DECIMAL(7,2),
    college_market_share DECIMAL(5,2),
    per_game_yards  DECIMAL(7,2),
    per_game_tds    DECIMAL(5,2),
    UNIQUE(player_name, college_team, season)
);

-- =========================================================================
-- Prospect Profiles
-- =========================================================================
CREATE TABLE IF NOT EXISTS prospect_profiles (
    id                          SERIAL PRIMARY KEY,
    player_id                   VARCHAR(20)    NOT NULL,
    player_name                 VARCHAR(100)   NOT NULL,
    college                     VARCHAR(50)    NOT NULL,
    conference                  VARCHAR(20)    NOT NULL,
    position                    VARCHAR(3)     NOT NULL,
    draft_season                INTEGER        NOT NULL,
    draft_round                 INTEGER,
    draft_pick                  INTEGER,
    scheme_familiarity_score    DECIMAL(5,2),
    conference_adjustment       DECIMAL(5,2),
    prospect_comp_ceiling       DECIMAL(6,2),
    prospect_comp_floor         DECIMAL(6,2),
    prospect_comp_median        DECIMAL(6,2),
    prospect_comp_bust_rate     DECIMAL(5,2),
    years_to_breakout_comp      DECIMAL(5,2),
    college_teammates_on_roster INTEGER,
    UNIQUE(player_id, draft_season)
);

-- =========================================================================
-- Game Results (Historical Archive)
-- =========================================================================
CREATE TABLE IF NOT EXISTS game_results (
    id              SERIAL PRIMARY KEY,
    game_id         VARCHAR(30)    NOT NULL UNIQUE,
    season          INTEGER        NOT NULL,
    week            INTEGER        NOT NULL,
    home_team       VARCHAR(5)     NOT NULL,
    away_team       VARCHAR(5)     NOT NULL,
    home_score      INTEGER,
    away_score      INTEGER,
    winner          VARCHAR(5),
    total_points    INTEGER,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- =========================================================================
-- Game Player Stats (Fantasy Stats Archive)
-- =========================================================================
CREATE TABLE IF NOT EXISTS game_player_stats (
    id                         SERIAL PRIMARY KEY,
    game_id                    VARCHAR(30)    NOT NULL,
    player_id                  VARCHAR(20)    NOT NULL,
    player_name                VARCHAR(100)   NOT NULL,
    team                       VARCHAR(5)     NOT NULL,
    position                   VARCHAR(3)     NOT NULL,
    fantasy_points_half_ppr    DECIMAL(6,2),
    fantasy_points_ppr         DECIMAL(6,2),
    fantasy_points_standard    DECIMAL(6,2),
    passing_yards              DECIMAL(7,2),
    passing_tds                DECIMAL(5,2),
    rushing_yards              DECIMAL(7,2),
    rushing_tds                DECIMAL(5,2),
    receptions                 DECIMAL(5,2),
    receiving_yards            DECIMAL(7,2),
    receiving_tds              DECIMAL(5,2),
    targets                    INTEGER,
    carries                    INTEGER,
    created_at                 TIMESTAMP DEFAULT NOW(),
    UNIQUE(game_id, player_id)
);

-- =========================================================================
-- Indexes
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_projections_season_week
    ON projections(season, week);
CREATE INDEX IF NOT EXISTS idx_projections_position
    ON projections(position);
CREATE INDEX IF NOT EXISTS idx_projections_team
    ON projections(team);
CREATE INDEX IF NOT EXISTS idx_projections_scoring
    ON projections(scoring_format);
CREATE INDEX IF NOT EXISTS idx_projections_player
    ON projections(player_id);

CREATE INDEX IF NOT EXISTS idx_predictions_season_week
    ON predictions(season, week);
CREATE INDEX IF NOT EXISTS idx_predictions_teams
    ON predictions(home_team, away_team);

CREATE INDEX IF NOT EXISTS idx_college_player_stats_season
    ON college_player_stats(season);
CREATE INDEX IF NOT EXISTS idx_college_player_stats_position
    ON college_player_stats(position);
CREATE INDEX IF NOT EXISTS idx_college_player_stats_conference
    ON college_player_stats(conference);

CREATE INDEX IF NOT EXISTS idx_prospect_profiles_season
    ON prospect_profiles(draft_season);
CREATE INDEX IF NOT EXISTS idx_prospect_profiles_position
    ON prospect_profiles(position);
CREATE INDEX IF NOT EXISTS idx_prospect_profiles_player_id
    ON prospect_profiles(player_id);

CREATE INDEX IF NOT EXISTS idx_game_results_season_week
    ON game_results(season, week);
CREATE INDEX IF NOT EXISTS idx_game_results_teams
    ON game_results(home_team, away_team);

CREATE INDEX IF NOT EXISTS idx_game_player_stats_game_id
    ON game_player_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_game_player_stats_player_id
    ON game_player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_game_player_stats_position
    ON game_player_stats(position);
