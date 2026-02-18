import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dashboard.data import (
    load_player_list, load_player_weekly,
    load_player_season_summary, POSITION_COLORS,
)

st.set_page_config(page_title="Player Explorer", page_icon="🔍", layout="wide")
st.title("🔍 Player Explorer")

# ── Sidebar filters ────────────────────────────────────────────────────────
with st.sidebar:
    position = st.selectbox("Position", ["QB", "RB", "WR", "TE"])
    players  = load_player_list(position)
    player_name = st.selectbox(
        "Player",
        players["player_name"].tolist(),
        index=0,
    )
    player_row  = players[players["player_name"] == player_name].iloc[0]
    player_id   = player_row["player_id"]

    seasons = st.multiselect(
        "Seasons",
        [2024, 2023, 2022, 2021, 2020],
        default=[2024, 2023],
    )

if not seasons:
    st.warning("Select at least one season.")
    st.stop()

weekly  = load_player_weekly(player_id, seasons)
summary = load_player_season_summary(player_id)
summary = summary[summary["season"].isin(seasons)]

if weekly.empty:
    st.info("No data for the selected player / seasons.")
    st.stop()

# ── KPI cards (aggregated across selected seasons) ─────────────────────────
st.subheader(f"{player_name}  ·  {position}  ·  {player_row['team']}")

total_ppr  = summary["total_fantasy_pts_ppr"].sum()
avg_ppr    = summary["avg_pts_per_game_ppr"].mean()
boom_rate  = summary["boom_rate_pct"].mean()
bust_rate  = summary["bust_rate_pct"].mean()
cv         = summary["consistency_cv"].mean()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total PPR Pts",     f"{total_ppr:,.1f}")
c2.metric("Avg Pts / Game",    f"{avg_ppr:.1f}")
c3.metric("Boom Rate",         f"{boom_rate:.1f}%")
c4.metric("Bust Rate",         f"{bust_rate:.1f}%")
c5.metric("Consistency (CV)",  f"{cv:.3f}", help="Lower = more consistent")

st.divider()

# ── Weekly fantasy points chart ────────────────────────────────────────────
weekly["label"] = weekly["season"].astype(str) + " Wk " + weekly["week"].astype(str)
color = POSITION_COLORS.get(position, "#888")

fig = go.Figure()

fig.add_trace(go.Bar(
    x=weekly["label"],
    y=weekly["fantasy_points_ppr"],
    name="Weekly PPR",
    marker_color=color,
    opacity=0.7,
))

fig.add_trace(go.Scatter(
    x=weekly["label"],
    y=weekly["rolling_4wk_ppr"],
    name="4-Wk Rolling Avg",
    mode="lines+markers",
    line=dict(color="white", width=2),
    marker=dict(size=4),
))

if "baseline_ppr" in weekly.columns:
    fig.add_trace(go.Scatter(
        x=weekly["label"],
        y=weekly["baseline_ppr"],
        name="Startable Baseline",
        mode="lines",
        line=dict(color="#f4a261", width=1.5, dash="dot"),
    ))

fig.update_layout(
    title="Weekly PPR Points vs. Rolling Average",
    xaxis_title="",
    yaxis_title="PPR Points",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=380,
    bargap=0.2,
)
fig.update_xaxes(tickangle=-45)
st.plotly_chart(fig, use_container_width=True)

# ── Snap share + target share ──────────────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    snap_data = weekly.dropna(subset=["snap_share"])
    if not snap_data.empty:
        fig2 = px.area(
            snap_data, x="label", y="snap_share",
            title="Snap Share %",
            labels={"snap_share": "Snap Share", "label": ""},
            color_discrete_sequence=[color],
        )
        fig2.update_yaxes(tickformat=".0%")
        fig2.update_xaxes(tickangle=-45)
        fig2.update_layout(height=300)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No snap share data available.")

with col_r:
    if position in ("WR", "TE", "RB"):
        ts_data = weekly.dropna(subset=["target_share"])
        if not ts_data.empty:
            fig3 = px.area(
                ts_data, x="label", y="target_share",
                title="Target Share %",
                labels={"target_share": "Target Share", "label": ""},
                color_discrete_sequence=["#f4a261"],
            )
            fig3.update_yaxes(tickformat=".0%")
            fig3.update_xaxes(tickangle=-45)
            fig3.update_layout(height=300)
            st.plotly_chart(fig3, use_container_width=True)
    else:
        pass_data = weekly[["label", "passing_epa"]].dropna()
        if not pass_data.empty:
            fig3 = px.bar(
                pass_data, x="label", y="passing_epa",
                title="Passing EPA / Week",
                labels={"passing_epa": "EPA", "label": ""},
                color_discrete_sequence=["#f4a261"],
            )
            fig3.update_xaxes(tickangle=-45)
            fig3.update_layout(height=300)
            st.plotly_chart(fig3, use_container_width=True)

# ── Weekly stats table ─────────────────────────────────────────────────────
with st.expander("Weekly Stats Table", expanded=False):
    display_cols = [
        "season", "week", "team", "opponent",
        "fantasy_points_ppr", "rolling_4wk_ppr", "weekly_position_rank",
        "snap_share", "target_share",
    ]
    available = [c for c in display_cols if c in weekly.columns]
    st.dataframe(
        weekly[available].rename(columns={
            "fantasy_points_ppr":  "PPR Pts",
            "rolling_4wk_ppr":     "4Wk Avg",
            "weekly_position_rank": "Pos Rank",
            "snap_share":          "Snap %",
            "target_share":        "Tgt Share",
        }),
        hide_index=True,
        use_container_width=True,
    )
