"""
Shared data-access layer for the Streamlit dashboard.
All queries return DataFrames and are cached by Streamlit.
"""

import duckdb
import streamlit as st
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "sleeper_analytics.duckdb"

POSITION_COLORS = {
    "QB": "#e63946",
    "RB": "#2a9d8f",
    "WR": "#457b9d",
    "TE": "#f4a261",
}

VARIANT_COLORS = {
    "control":   "#adb5bd",
    "treatment": "#00d1a0",
}


@st.cache_resource
def get_conn() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        st.error(f"Database not found at {DB_PATH}. Run `python run.py` first.")
        st.stop()
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data
def load_kpis() -> dict:
    con = get_conn()
    return {
        "players": con.execute(
            "SELECT COUNT(DISTINCT player_id) FROM metrics_player_weekly"
        ).fetchone()[0],
        "seasons": con.execute(
            "SELECT COUNT(DISTINCT season) FROM metrics_player_season"
        ).fetchone()[0],
        "games": con.execute("SELECT COUNT(*) FROM dim_games").fetchone()[0],
        "records": con.execute(
            "SELECT COUNT(*) FROM metrics_player_weekly"
        ).fetchone()[0],
    }


@st.cache_data
def load_top_players(season: int, n: int = 15):
    return get_conn().execute(f"""
        SELECT player_name, position, team,
               avg_pts_per_game_ppr, total_fantasy_pts_ppr,
               boom_rate_pct, bust_rate_pct, games_played
        FROM metrics_player_season
        WHERE season = {season}
          AND games_played >= 8
        ORDER BY avg_pts_per_game_ppr DESC
        LIMIT {n}
    """).df()


@st.cache_data
def load_player_list(position: str | None = None):
    where = f"WHERE position = '{position}'" if position else ""
    return get_conn().execute(f"""
        SELECT DISTINCT player_id, player_name, position, team
        FROM metrics_player_weekly
        {where}
        ORDER BY player_name
    """).df()


@st.cache_data
def load_player_weekly(player_id: str, seasons: list[int] | None = None):
    seasons_sql = (
        f"AND season IN ({','.join(map(str, seasons))})" if seasons else ""
    )
    return get_conn().execute(f"""
        SELECT w.*, b.avg_pts_startable AS baseline_ppr
        FROM metrics_player_weekly w
        LEFT JOIN metrics_position_baseline b
            ON b.position = w.position
           AND b.season   = w.season
           AND b.week     = w.week
        WHERE w.player_id = '{player_id}'
        {seasons_sql}
        ORDER BY season, week
    """).df()


@st.cache_data
def load_player_season_summary(player_id: str):
    return get_conn().execute(f"""
        SELECT *
        FROM metrics_player_season
        WHERE player_id = '{player_id}'
        ORDER BY season DESC
    """).df()


@st.cache_data
def load_leaderboard(season: int, position: str):
    return get_conn().execute(f"""
        SELECT
            season_position_rank   AS rank,
            player_name,
            team,
            games_played,
            ROUND(total_fantasy_pts_ppr, 1)  AS total_ppr,
            ROUND(avg_pts_per_game_ppr,  1)  AS avg_ppr,
            ROUND(ceiling_ppr, 1)            AS ceiling,
            ROUND(floor_ppr,   1)            AS floor,
            ROUND(boom_rate_pct, 1)          AS boom_pct,
            ROUND(bust_rate_pct, 1)          AS bust_pct,
            ROUND(consistency_cv, 3)         AS cv
        FROM metrics_player_season
        WHERE season = {season}
          AND position = '{position}'
          AND games_played >= 6
        ORDER BY rank
        LIMIT 40
    """).df()


@st.cache_data
def load_ab_weekly():
    return get_conn().execute("""
        SELECT
            week,
            variant,
            ROUND(AVG(made_claim)  * 100, 2) AS claim_rate_pct,
            ROUND(AVG(set_lineup)  * 100, 2) AS lineup_rate_pct,
            ROUND(AVG(retained)    * 100, 2) AS retention_pct,
            COUNT(*)                          AS n
        FROM ab_events
        GROUP BY week, variant
        ORDER BY week, variant
    """).df()


@st.cache_data
def load_ab_segment(col: str):
    return get_conn().execute(f"""
        SELECT
            {col}                             AS segment,
            variant,
            ROUND(AVG(made_claim) * 100, 2)  AS claim_rate_pct,
            ROUND(AVG(num_claims), 3)         AS avg_claims,
            COUNT(*)                          AS n
        FROM ab_events
        GROUP BY {col}, variant
        ORDER BY {col}, variant
    """).df()


@st.cache_data
def load_ab_kpis() -> dict:
    con = get_conn()

    def q(col, variant):
        return con.execute(
            f"SELECT AVG({col}) FROM ab_events WHERE variant='{variant}'"
        ).fetchone()[0]

    return {
        "claim_c":  q("made_claim", "control"),
        "claim_t":  q("made_claim", "treatment"),
        "claims_c": q("num_claims", "control"),
        "claims_t": q("num_claims", "treatment"),
        "lineup_c": q("set_lineup", "control"),
        "lineup_t": q("set_lineup", "treatment"),
        "retain_c": q("retained",   "control"),
        "retain_t": q("retained",   "treatment"),
    }
