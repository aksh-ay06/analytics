import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
from dashboard.data import DB_PATH, load_kpis, load_top_players, POSITION_COLORS

st.set_page_config(
    page_title="Sleeper Analytics",
    page_icon="🏈",
    layout="wide",
)

# ── DB bootstrap (runs once on cold start, e.g. Streamlit Cloud) ──────────
if not DB_PATH.exists():
    st.info("First run — building the database. This takes about 2 minutes.")
    progress = st.progress(0, text="Starting pipeline...")

    from pipeline.ingest import run_ingestion
    from pipeline.transform import run_transforms
    from pipeline.metrics import run_metrics
    from analysis.simulate import run_simulation

    progress.progress(10, text="Ingesting NFL data (seasons 2020–2024)...")
    con = run_ingestion()

    progress.progress(50, text="Building dimension and fact tables...")
    run_transforms(con)

    progress.progress(75, text="Computing metrics...")
    run_metrics(con)

    progress.progress(90, text="Simulating A/B experiment...")
    run_simulation(con)
    con.close()

    progress.progress(100, text="Done!")
    st.rerun()

st.title("🏈 Sleeper Fantasy Analytics")
st.caption(
    "NFL seasons 2020–2024  ·  QB / RB / WR / TE  ·  "
    "Powered by nfl_data_py + DuckDB"
)

# ── KPI row ────────────────────────────────────────────────────────────────
kpis = load_kpis()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Players Tracked",  f"{kpis['players']:,}")
c2.metric("Seasons",           kpis["seasons"])
c3.metric("NFL Games",         f"{kpis['games']:,}")
c4.metric("Weekly Records",    f"{kpis['records']:,}")

st.divider()

# ── Top players chart ──────────────────────────────────────────────────────
col_chart, col_side = st.columns([3, 1])

with col_side:
    season = st.selectbox("Season", [2024, 2023, 2022, 2021, 2020])
    positions = st.multiselect(
        "Positions",
        ["QB", "RB", "WR", "TE"],
        default=["QB", "RB", "WR", "TE"],
    )
    n = st.slider("Show top N", 5, 30, 15)

df = load_top_players(season, n=30)
if positions:
    df = df[df["position"].isin(positions)]
df = df.head(n).sort_values("avg_pts_per_game_ppr")

with col_chart:
    fig = px.bar(
        df,
        x="avg_pts_per_game_ppr",
        y="player_name",
        color="position",
        color_discrete_map=POSITION_COLORS,
        orientation="h",
        text=df["avg_pts_per_game_ppr"].round(1),
        title=f"Top {n} Players by Avg PPR Points / Game — {season}",
        labels={
            "avg_pts_per_game_ppr": "Avg PPR Pts / Game",
            "player_name": "",
            "position": "Position",
        },
        height=max(400, n * 28),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        xaxis_title="Avg PPR Pts / Game",
        yaxis_title="",
        legend_title="Position",
        margin=dict(l=10, r=60, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Position breakdown strip ────────────────────────────────────────────────
st.divider()
st.subheader(f"Position Snapshot — {season}")

for pos in ["QB", "RB", "WR", "TE"]:
    pos_df = df[df["position"] == pos].head(3)
    if pos_df.empty:
        continue
    with st.expander(f"**{pos}** — top 3", expanded=False):
        st.dataframe(
            pos_df[["player_name", "team", "avg_pts_per_game_ppr",
                    "boom_rate_pct", "bust_rate_pct", "games_played"]]
            .rename(columns={
                "player_name":        "Player",
                "team":               "Team",
                "avg_pts_per_game_ppr": "Avg PPR",
                "boom_rate_pct":      "Boom %",
                "bust_rate_pct":      "Bust %",
                "games_played":       "GP",
            }),
            hide_index=True,
            use_container_width=True,
        )
