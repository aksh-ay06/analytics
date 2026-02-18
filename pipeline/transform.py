"""
Transformation layer.
Reads raw tables from DuckDB, cleans and models them into
analysis-ready dimension and fact tables.
"""

import duckdb
from pipeline.ingest import get_connection

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def build_dim_players(con: duckdb.DuckDBPyConnection) -> None:
    """
    Player dimension table.
    One row per player_id, using the most recent roster entry.
    Includes sleeper_id for direct mapping to the Sleeper platform.
    """
    print("Building dim_players...")
    con.execute("""
        CREATE OR REPLACE TABLE dim_players AS
        SELECT
            player_id,
            sleeper_id,
            player_name,
            first_name,
            last_name,
            position,
            college,
            birth_date::DATE        AS birth_date,
            height,
            weight::FLOAT           AS weight,
            years_exp,
            entry_year,
            rookie_year,
            draft_club,
            draft_number::INTEGER   AS draft_number
        FROM (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY player_id
                    ORDER BY season DESC, week DESC
                ) AS rn
            FROM raw_rosters
            WHERE player_id IS NOT NULL
        )
        WHERE rn = 1
    """)
    count = con.execute("SELECT COUNT(*) FROM dim_players").fetchone()[0]
    print(f"  {count:,} rows in dim_players")


def build_dim_games(con: duckdb.DuckDBPyConnection) -> None:
    """
    Game dimension table from schedules.
    One row per game.
    """
    print("Building dim_games...")
    con.execute("""
        CREATE OR REPLACE TABLE dim_games AS
        SELECT
            game_id,
            season,
            week,
            game_type,
            gameday::DATE   AS gameday,
            weekday,
            gametime,
            away_team,
            home_team,
            away_score::INTEGER     AS away_score,
            home_score::INTEGER     AS home_score,
            result::FLOAT           AS result,
            total::FLOAT            AS total,
            overtime::BOOLEAN       AS overtime,
            div_game::BOOLEAN       AS div_game,
            roof,
            surface,
            temp::FLOAT             AS temp,
            wind::FLOAT             AS wind,
            stadium,
            away_coach,
            home_coach,
            spread_line::FLOAT      AS spread_line,
            total_line::FLOAT       AS total_line
        FROM raw_schedules
        WHERE game_id IS NOT NULL
    """)
    count = con.execute("SELECT COUNT(*) FROM dim_games").fetchone()[0]
    print(f"  {count:,} rows in dim_games")


def build_fact_weekly_stats(con: duckdb.DuckDBPyConnection) -> None:
    """
    Weekly player performance fact table.
    Filtered to skill positions (QB, RB, WR, TE) and regular season only.
    """
    print("Building fact_weekly_stats...")
    con.execute(f"""
        CREATE OR REPLACE TABLE fact_weekly_stats AS
        SELECT
            player_id,
            player_display_name          AS player_name,
            position,
            recent_team                  AS team,
            opponent_team                AS opponent,
            season,
            week,
            -- Passing
            completions,
            attempts,
            passing_yards,
            passing_tds,
            interceptions,
            passing_air_yards,
            passing_yards_after_catch,
            passing_first_downs,
            passing_epa,
            -- Rushing
            carries,
            rushing_yards,
            rushing_tds,
            rushing_first_downs,
            rushing_epa,
            -- Receiving
            receptions,
            targets,
            receiving_yards,
            receiving_tds,
            receiving_air_yards,
            receiving_yards_after_catch,
            receiving_first_downs,
            receiving_epa,
            target_share,
            air_yards_share,
            wopr,
            -- Fantasy
            fantasy_points,
            fantasy_points_ppr,
            -- Fumbles
            rushing_fumbles + receiving_fumbles + sack_fumbles          AS total_fumbles,
            rushing_fumbles_lost + receiving_fumbles_lost
                + sack_fumbles_lost                                      AS total_fumbles_lost
        FROM raw_weekly_stats
        WHERE season_type = 'REG'
          AND position IN {SKILL_POSITIONS}
          AND player_id IS NOT NULL
    """)
    count = con.execute("SELECT COUNT(*) FROM fact_weekly_stats").fetchone()[0]
    print(f"  {count:,} rows in fact_weekly_stats")


def build_fact_snap_counts(con: duckdb.DuckDBPyConnection) -> None:
    """
    Weekly offensive snap count fact table.
    Filters to offensive skill positions only.
    """
    print("Building fact_snap_counts...")
    con.execute(f"""
        CREATE OR REPLACE TABLE fact_snap_counts AS
        SELECT
            game_id,
            season,
            week,
            game_type,
            player                      AS player_name,
            pfr_player_id,
            position,
            team,
            opponent,
            offense_snaps::INTEGER      AS offense_snaps,
            offense_pct::FLOAT          AS offense_pct
        FROM raw_snap_counts
        WHERE game_type = 'REG'
          AND position IN {SKILL_POSITIONS}
          AND offense_snaps > 0
    """)
    count = con.execute("SELECT COUNT(*) FROM fact_snap_counts").fetchone()[0]
    print(f"  {count:,} rows in fact_snap_counts")


def run_transforms(con: duckdb.DuckDBPyConnection = None) -> duckdb.DuckDBPyConnection:
    if con is None:
        con = get_connection()
    build_dim_players(con)
    build_dim_games(con)
    build_fact_weekly_stats(con)
    build_fact_snap_counts(con)
    print("\nTransformations complete.")
    return con


if __name__ == "__main__":
    run_transforms()
