"""
Metrics layer.
Computes derived analytics on top of fact and dimension tables.

Tables produced:
  - metrics_player_weekly   per-player, per-week derived stats + rolling trends
  - metrics_player_season   season-level aggregates, consistency, boom/bust rates
  - metrics_position_baseline  positional averages for relative ranking
"""

import duckdb
from pipeline.ingest import get_connection


# Fantasy scoring thresholds for boom/bust classification
BOOM_THRESHOLD_PPR = {"QB": 30.0, "RB": 20.0, "WR": 20.0, "TE": 15.0}
BUST_THRESHOLD_PPR = {"QB": 10.0, "RB": 5.0,  "WR": 5.0,  "TE": 3.0}
ROLLING_WINDOW = 4  # weeks


def build_metrics_player_weekly(con: duckdb.DuckDBPyConnection) -> None:
    """
    Weekly player metrics with rolling averages and usage rates.
    Joins fact_weekly_stats with fact_snap_counts for snap share.
    """
    print("Building metrics_player_weekly...")
    con.execute(f"""
        CREATE OR REPLACE TABLE metrics_player_weekly AS
        WITH snap_agg AS (
            -- Aggregate snap data to match weekly_stats grain (player_name + team + season + week)
            SELECT
                player_name,
                team,
                season,
                week,
                SUM(offense_snaps) AS offense_snaps,
                MAX(offense_pct)   AS snap_share
            FROM fact_snap_counts
            GROUP BY player_name, team, season, week
        ),
        weekly_base AS (
            SELECT
                w.player_id,
                w.player_name,
                w.position,
                w.team,
                w.opponent,
                w.season,
                w.week,

                -- Fantasy
                w.fantasy_points,
                w.fantasy_points_ppr,

                -- Passing efficiency
                CASE WHEN w.attempts > 0
                    THEN ROUND(w.passing_yards / w.attempts, 2) END           AS yards_per_attempt,
                CASE WHEN w.attempts > 0
                    THEN ROUND(w.passing_tds::FLOAT / w.attempts * 100, 2) END AS td_rate_pct,
                CASE WHEN w.attempts > 0
                    THEN ROUND(w.interceptions::FLOAT / w.attempts * 100, 2) END AS int_rate_pct,
                w.passing_epa,

                -- Rushing efficiency
                CASE WHEN w.carries > 0
                    THEN ROUND(w.rushing_yards / w.carries, 2) END            AS yards_per_carry,
                w.rushing_epa,

                -- Receiving efficiency
                CASE WHEN w.targets > 0
                    THEN ROUND(w.receptions::FLOAT / w.targets * 100, 2) END  AS catch_rate_pct,
                CASE WHEN w.targets > 0
                    THEN ROUND(w.receiving_yards / w.targets, 2) END           AS yards_per_target,
                CASE WHEN w.targets > 0
                    THEN ROUND(w.receiving_yards / w.receptions, 2) END        AS yards_per_reception,
                w.target_share,
                w.air_yards_share,
                w.wopr,
                w.receiving_epa,

                -- Touches / opportunity
                (w.carries + w.receptions)                                    AS touches,
                (w.carries + w.targets)                                       AS opportunities,
                w.total_fumbles_lost,

                -- Snap share from snap_counts
                s.offense_snaps,
                s.snap_share

            FROM fact_weekly_stats w
            LEFT JOIN snap_agg s
                ON  s.player_name = w.player_name
                AND s.team        = w.team
                AND s.season      = w.season
                AND s.week        = w.week
        ),
        rolling AS (
            SELECT
                *,
                -- Rolling {ROLLING_WINDOW}-week PPR average
                ROUND(AVG(fantasy_points_ppr) OVER (
                    PARTITION BY player_id
                    ORDER BY season, week
                    ROWS BETWEEN {ROLLING_WINDOW - 1} PRECEDING AND CURRENT ROW
                ), 2) AS rolling_{ROLLING_WINDOW}wk_ppr,

                -- Rolling 4-week snap share
                ROUND(AVG(snap_share) OVER (
                    PARTITION BY player_id
                    ORDER BY season, week
                    ROWS BETWEEN {ROLLING_WINDOW - 1} PRECEDING AND CURRENT ROW
                ), 3) AS rolling_{ROLLING_WINDOW}wk_snap_share,

                -- Week-over-week PPR delta
                ROUND(
                    fantasy_points_ppr - LAG(fantasy_points_ppr) OVER (
                        PARTITION BY player_id ORDER BY season, week
                    ), 2
                ) AS wow_ppr_delta,

                -- Season rank by PPR within position + week
                RANK() OVER (
                    PARTITION BY position, season, week
                    ORDER BY fantasy_points_ppr DESC
                ) AS weekly_position_rank
            FROM weekly_base
        )
        SELECT * FROM rolling
    """)
    count = con.execute("SELECT COUNT(*) FROM metrics_player_weekly").fetchone()[0]
    print(f"  {count:,} rows in metrics_player_weekly")


def build_metrics_player_season(con: duckdb.DuckDBPyConnection) -> None:
    """
    Season-level player aggregates.
    Includes consistency score, boom/bust rates, and positional rank.
    """
    print("Building metrics_player_season...")

    # Build CASE expressions for boom/bust using position-specific thresholds
    boom_cases = " ".join([
        f"WHEN position = '{pos}' THEN (fantasy_points_ppr >= {thresh})"
        for pos, thresh in BOOM_THRESHOLD_PPR.items()
    ])
    bust_cases = " ".join([
        f"WHEN position = '{pos}' THEN (fantasy_points_ppr <= {thresh})"
        for pos, thresh in BUST_THRESHOLD_PPR.items()
    ])

    con.execute(f"""
        CREATE OR REPLACE TABLE metrics_player_season AS
        WITH game_flags AS (
            SELECT
                player_id,
                player_name,
                position,
                season,
                week,
                team,
                fantasy_points,
                fantasy_points_ppr,
                CASE {boom_cases} END AS is_boom,
                CASE {bust_cases} END AS is_bust
            FROM metrics_player_weekly
        ),
        season_agg AS (
            SELECT
                player_id,
                player_name,
                position,
                season,
                LAST(team ORDER BY week)                                AS team,
                COUNT(*)                                                AS games_played,
                ROUND(SUM(fantasy_points),     2)                      AS total_fantasy_pts,
                ROUND(SUM(fantasy_points_ppr), 2)                      AS total_fantasy_pts_ppr,
                ROUND(AVG(fantasy_points_ppr), 2)                      AS avg_pts_per_game_ppr,
                ROUND(STDDEV(fantasy_points_ppr), 2)                   AS consistency_stddev,
                -- Coefficient of variation: lower = more consistent
                ROUND(
                    STDDEV(fantasy_points_ppr) / NULLIF(AVG(fantasy_points_ppr), 0),
                    3
                )                                                       AS consistency_cv,
                ROUND(SUM(CAST(is_boom AS INTEGER))::FLOAT
                    / COUNT(*) * 100, 1)                               AS boom_rate_pct,
                ROUND(SUM(CAST(is_bust AS INTEGER))::FLOAT
                    / COUNT(*) * 100, 1)                               AS bust_rate_pct,
                ROUND(MAX(fantasy_points_ppr), 2)                      AS ceiling_ppr,
                ROUND(MIN(fantasy_points_ppr), 2)                      AS floor_ppr
            FROM game_flags g
            GROUP BY player_id, player_name, position, season
        )
        SELECT
            s.*,
            RANK() OVER (
                PARTITION BY position, season
                ORDER BY total_fantasy_pts_ppr DESC
            ) AS season_position_rank
        FROM season_agg s
    """)
    count = con.execute("SELECT COUNT(*) FROM metrics_player_season").fetchone()[0]
    print(f"  {count:,} rows in metrics_player_season")


def build_metrics_position_baseline(con: duckdb.DuckDBPyConnection) -> None:
    """
    Positional baseline averages per season and week.
    Used to compute relative performance (points above/below baseline).
    Top 24 QB, 48 RB, 48 WR, 24 TE qualify as 'startable' in a 12-team league.
    """
    print("Building metrics_position_baseline...")
    startable_counts = {"QB": 24, "RB": 48, "WR": 48, "TE": 24}

    cases = " ".join([
        f"WHEN position = '{pos}' THEN {n}"
        for pos, n in startable_counts.items()
    ])

    con.execute(f"""
        CREATE OR REPLACE TABLE metrics_position_baseline AS
        WITH ranked AS (
            SELECT
                position,
                season,
                week,
                fantasy_points_ppr,
                weekly_position_rank,
                CASE {cases} END AS startable_threshold
            FROM metrics_player_weekly
        ),
        baseline AS (
            SELECT
                position,
                season,
                week,
                ROUND(AVG(fantasy_points_ppr), 2)                         AS avg_pts_all,
                ROUND(AVG(CASE WHEN weekly_position_rank <= startable_threshold
                    THEN fantasy_points_ppr END), 2)                       AS avg_pts_startable,
                ROUND(MAX(fantasy_points_ppr), 2)                          AS max_pts,
                COUNT(DISTINCT weekly_position_rank)                       AS players_with_data
            FROM ranked
            GROUP BY position, season, week
        )
        SELECT * FROM baseline
    """)
    count = con.execute("SELECT COUNT(*) FROM metrics_position_baseline").fetchone()[0]
    print(f"  {count:,} rows in metrics_position_baseline")


def run_metrics(con: duckdb.DuckDBPyConnection = None) -> duckdb.DuckDBPyConnection:
    if con is None:
        con = get_connection()
    build_metrics_player_weekly(con)
    build_metrics_player_season(con)
    build_metrics_position_baseline(con)
    print("\nMetrics layer complete.")
    return con


if __name__ == "__main__":
    run_metrics()
