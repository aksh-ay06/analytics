"""
Raw data ingestion layer.
Pulls NFL data via nfl_data_py and loads it into DuckDB.
"""

import nfl_data_py as nfl
import duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "sleeper_analytics.duckdb"
SEASONS = list(range(2020, 2025))


def get_connection() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def ingest_weekly_stats(con: duckdb.DuckDBPyConnection) -> None:
    print(f"Ingesting weekly player stats for seasons {SEASONS}...")
    df = nfl.import_weekly_data(SEASONS)
    df.columns = df.columns.str.lower()
    con.execute("DROP TABLE IF EXISTS raw_weekly_stats")
    con.execute("CREATE TABLE raw_weekly_stats AS SELECT * FROM df")
    print(f"  Loaded {len(df):,} rows into raw_weekly_stats")


def ingest_rosters(con: duckdb.DuckDBPyConnection) -> None:
    print(f"Ingesting roster data for seasons {SEASONS}...")
    df = nfl.import_weekly_rosters(SEASONS)
    df.columns = df.columns.str.lower()
    con.execute("DROP TABLE IF EXISTS raw_rosters")
    con.execute("CREATE TABLE raw_rosters AS SELECT * FROM df")
    print(f"  Loaded {len(df):,} rows into raw_rosters")


def ingest_schedules(con: duckdb.DuckDBPyConnection) -> None:
    print(f"Ingesting game schedules for seasons {SEASONS}...")
    df = nfl.import_schedules(SEASONS)
    df.columns = df.columns.str.lower()
    con.execute("DROP TABLE IF EXISTS raw_schedules")
    con.execute("CREATE TABLE raw_schedules AS SELECT * FROM df")
    print(f"  Loaded {len(df):,} rows into raw_schedules")


def ingest_snap_counts(con: duckdb.DuckDBPyConnection) -> None:
    print(f"Ingesting snap counts for seasons {SEASONS}...")
    df = nfl.import_snap_counts(SEASONS)
    df.columns = df.columns.str.lower()
    con.execute("DROP TABLE IF EXISTS raw_snap_counts")
    con.execute("CREATE TABLE raw_snap_counts AS SELECT * FROM df")
    print(f"  Loaded {len(df):,} rows into raw_snap_counts")


def run_ingestion() -> duckdb.DuckDBPyConnection:
    con = get_connection()
    ingest_weekly_stats(con)
    ingest_rosters(con)
    ingest_schedules(con)
    ingest_snap_counts(con)
    print("\nIngestion complete.")
    return con


if __name__ == "__main__":
    run_ingestion()
