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
