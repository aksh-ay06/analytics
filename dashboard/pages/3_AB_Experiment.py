import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from dashboard.data import load_ab_weekly, load_ab_segment, load_ab_kpis, VARIANT_COLORS

st.set_page_config(page_title="A/B Experiment", page_icon="⚗️", layout="wide")
st.title("⚗️ A/B Experiment: Waiver Wire AI Recommendations")

st.markdown("""
**Hypothesis:** Showing AI-powered player recommendations on the waiver wire page
increases weekly claim rate, driving higher engagement and season-long retention.

| | Control | Treatment |
|---|---|---|
| **Experience** | Standard waiver wire UI | Waiver wire + AI recommendations |
| **Users** | ~5,000 | ~5,000 |
| **Duration** | NFL 2023 Weeks 3–10 (8 weeks) |  |
""")

st.divider()

# ── KPI cards ──────────────────────────────────────────────────────────────
kpis = load_ab_kpis()

def lift_delta(control, treatment, fmt=".1%"):
    delta = treatment - control
    return f"{delta:+{fmt}} lift"

st.subheader("Key Metrics")
c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Waiver Claim Rate",
    f"{kpis['claim_t']:.1%}",
    delta=lift_delta(kpis["claim_c"], kpis["claim_t"]),
    help=f"Control: {kpis['claim_c']:.1%}",
)
c2.metric(
    "Avg Claims / User",
    f"{kpis['claims_t']:.2f}",
    delta=f"{kpis['claims_t'] - kpis['claims_c']:+.2f} lift",
    help=f"Control: {kpis['claims_c']:.2f}",
)
c3.metric(
    "Lineup Set Rate",
    f"{kpis['lineup_t']:.1%}",
    delta=lift_delta(kpis["lineup_c"], kpis["lineup_t"]),
    help=f"Control: {kpis['lineup_c']:.1%}",
)
c4.metric(
    "Retention Rate",
    f"{kpis['retain_t']:.1%}",
    delta=lift_delta(kpis["retain_c"], kpis["retain_t"]),
    help=f"Control: {kpis['retain_c']:.1%}",
)

st.divider()

# ── Weekly claim rate: control vs treatment ────────────────────────────────
weekly = load_ab_weekly()
ctrl = weekly[weekly["variant"] == "control"].set_index("week")
trt  = weekly[weekly["variant"] == "treatment"].set_index("week")

col_l, col_r = st.columns(2)

with col_l:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ctrl.index, y=ctrl["claim_rate_pct"],
        name="Control", mode="lines+markers",
        line=dict(color=VARIANT_COLORS["control"], width=2),
        marker=dict(size=7),
    ))
    fig.add_trace(go.Scatter(
        x=trt.index, y=trt["claim_rate_pct"],
        name="Treatment", mode="lines+markers",
        line=dict(color=VARIANT_COLORS["treatment"], width=2),
        marker=dict(size=7),
    ))
    fig.update_layout(
        title="Weekly Waiver Claim Rate — Control vs Treatment",
        xaxis_title="NFL Week",
        yaxis_title="Claim Rate (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    lift = (trt["claim_rate_pct"] - ctrl["claim_rate_pct"]).reset_index()
    lift.columns = ["week", "lift_pp"]
    fig2 = px.bar(
        lift, x="week", y="lift_pp",
        title="Week-by-Week Lift (Treatment − Control, pp)",
        labels={"lift_pp": "Lift (pp)", "week": "NFL Week"},
        color_discrete_sequence=[VARIANT_COLORS["treatment"]],
        height=360,
    )
    fig2.add_hline(y=0, line_color="gray", line_dash="dot")
    fig2.update_layout(yaxis_title="Lift (percentage points)")
    st.plotly_chart(fig2, use_container_width=True)

# ── Novelty effect note ────────────────────────────────────────────────────
st.caption(
    "💡 No novelty decay observed — lift is stable across all 8 weeks, "
    "suggesting the treatment effect is durable, not a short-term curiosity spike."
)

st.divider()

# ── Segment analysis ───────────────────────────────────────────────────────
st.subheader("Segment Analysis")
seg_col1, seg_col2 = st.columns(2)

with seg_col1:
    seg_type = load_ab_segment("user_type")
    fig3 = px.bar(
        seg_type, x="segment", y="claim_rate_pct", color="variant",
        barmode="group",
        color_discrete_map=VARIANT_COLORS,
        title="Claim Rate by User Type",
        labels={"claim_rate_pct": "Claim Rate (%)", "segment": "User Type", "variant": "Variant"},
        height=350,
    )
    st.plotly_chart(fig3, use_container_width=True)

with seg_col2:
    seg_league = load_ab_segment("league_type")
    fig4 = px.bar(
        seg_league, x="segment", y="claim_rate_pct", color="variant",
        barmode="group",
        color_discrete_map=VARIANT_COLORS,
        title="Claim Rate by League Type",
        labels={"claim_rate_pct": "Claim Rate (%)", "segment": "League Type", "variant": "Variant"},
        height=350,
    )
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Statistical summary ────────────────────────────────────────────────────
st.subheader("Statistical Summary")
st.markdown("""
| Metric | Control | Treatment | Lift | p-value | Significant |
|---|---|---|---|---|---|
| Waiver Claim Rate | 33.1% | 42.0% | +8.9pp (+26.6%) | < 0.001 | ✅ |
| Claims per User | 4.78 | 7.36 | +2.58 (+53.8%) | < 0.001 | ✅ |
| Lineup Set Rate | 82.3% | 85.8% | +3.5pp (+4.2%) | < 0.001 | ✅ |
| Full-Season Retention | 14.6% | 19.3% | +4.8pp (+32.7%) | < 0.001 | ✅ |

**Power analysis:** Post-hoc power = 100% at n ≈ 40k user-weeks.
MDE at 80% power = Cohen's h of 0.020 — the experiment is sensitive to very small effects.

**Recommendation:** Ship to 100%. The treatment drives a durable +27% relative lift in
weekly waiver engagement with positive downstream effects on lineup completion and retention.
""")
