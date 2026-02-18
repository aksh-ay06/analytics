import streamlit as st
import plotly.express as px
from dashboard.data import load_leaderboard, POSITION_COLORS

st.set_page_config(page_title="Leaderboards", page_icon="🏆", layout="wide")
st.title("🏆 Season Leaderboards")

# ── Controls ───────────────────────────────────────────────────────────────
col_a, col_b, _ = st.columns([1, 1, 4])
with col_a:
    season = st.selectbox("Season", [2024, 2023, 2022, 2021, 2020])
with col_b:
    min_games = st.number_input("Min games played", 1, 17, 6)

tabs = st.tabs(["QB", "RB", "WR", "TE"])
positions = ["QB", "RB", "WR", "TE"]

for tab, pos in zip(tabs, positions):
    with tab:
        df = load_leaderboard(season, pos)
        df = df[df["games_played"] >= min_games].reset_index(drop=True)

        if df.empty:
            st.info("No data for this filter.")
            continue

        # ── Summary metrics ────────────────────────────────────────────────
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Players qualified", len(df))
        m2.metric("Avg PPR / game",    f"{df['avg_ppr'].mean():.1f}")
        m3.metric("Avg boom rate",     f"{df['boom_pct'].mean():.1f}%")
        m4.metric("Avg consistency CV", f"{df['cv'].mean():.3f}")

        # ── Leaderboard table ──────────────────────────────────────────────
        st.dataframe(
            df.rename(columns={
                "rank":         "Rank",
                "player_name":  "Player",
                "team":         "Team",
                "games_played": "GP",
                "total_ppr":    "Total PPR",
                "avg_ppr":      "Avg PPR",
                "ceiling":      "Ceiling",
                "floor":        "Floor",
                "boom_pct":     "Boom %",
                "bust_pct":     "Bust %",
                "cv":           "CV",
            }),
            hide_index=True,
            use_container_width=True,
            height=400,
        )

        st.divider()

        # ── Scatter: avg PPR vs boom rate ──────────────────────────────────
        col_l, col_r = st.columns(2)

        with col_l:
            fig = px.scatter(
                df.head(30),
                x="avg_ppr",
                y="boom_pct",
                size="games_played",
                text="player_name",
                color_discrete_sequence=[POSITION_COLORS[pos]],
                title=f"{pos} — Avg PPR vs Boom Rate",
                labels={
                    "avg_ppr":  "Avg PPR Pts / Game",
                    "boom_pct": "Boom Rate (%)",
                },
                height=400,
            )
            fig.update_traces(textposition="top center", textfont_size=9)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            # Ceiling vs floor risk/reward quadrant
            df_plot = df.head(30).copy()
            df_plot["range"] = df_plot["ceiling"] - df_plot["floor"]

            fig2 = px.scatter(
                df_plot,
                x="floor",
                y="ceiling",
                size="range",
                text="player_name",
                color="avg_ppr",
                color_continuous_scale="Teal",
                title=f"{pos} — Ceiling vs Floor (Risk / Reward)",
                labels={
                    "floor":   "Floor (min weekly PPR)",
                    "ceiling": "Ceiling (max weekly PPR)",
                    "avg_ppr": "Avg PPR",
                },
                height=400,
            )
            fig2.update_traces(textposition="top center", textfont_size=9)
            # Add diagonal guide line
            max_val = max(df_plot["ceiling"].max(), df_plot["floor"].max())
            fig2.add_shape(
                type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                line=dict(color="gray", dash="dot", width=1),
            )
            st.plotly_chart(fig2, use_container_width=True)
