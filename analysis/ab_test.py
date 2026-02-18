"""
A/B test statistical analysis module.

Tests run:
  1. Sample Ratio Mismatch (SRM) — chi-square goodness of fit
  2. Primary metric   — waiver claim rate (two-proportion z-test)
  3. Secondary metric — claims per user (Welch's t-test)
  4. Secondary metric — lineup set rate (two-proportion z-test)
  5. Secondary metric — week-1 retention (two-proportion z-test)
  6. Novelty effect check — week-by-week claim rate lift
  7. Segment analysis — by user_type and league_type
  8. Power analysis — post-hoc power + MDE for observed sample size
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
import duckdb
from scipy import stats

from pipeline.ingest import get_connection

ALPHA = 0.05


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ProportionTestResult:
    metric:       str
    p_control:    float
    p_treatment:  float
    n_control:    int
    n_treatment:  int
    lift_pp:      float          # absolute lift in percentage points
    lift_rel_pct: float          # relative lift %
    ci_lower:     float
    ci_upper:     float
    z_stat:       float
    p_value:      float
    cohens_h:     float
    significant:  bool

    def __str__(self) -> str:
        sig = "✓ SIGNIFICANT" if self.significant else "✗ not significant"
        return (
            f"\n  {self.metric}\n"
            f"    Control:    {self.p_control:.1%}  (n={self.n_control:,})\n"
            f"    Treatment:  {self.p_treatment:.1%}  (n={self.n_treatment:,})\n"
            f"    Lift:       {self.lift_pp:+.2f}pp  ({self.lift_rel_pct:+.1f}% relative)\n"
            f"    95% CI:     [{self.ci_lower:+.2f}pp, {self.ci_upper:+.2f}pp]\n"
            f"    z={self.z_stat:.3f}  p={self.p_value:.4f}  Cohen's h={self.cohens_h:.3f}\n"
            f"    Decision:   {sig}"
        )


@dataclass
class ContinuousTestResult:
    metric:       str
    mean_control:   float
    mean_treatment: float
    n_control:    int
    n_treatment:  int
    lift_abs:     float
    lift_rel_pct: float
    ci_lower:     float
    ci_upper:     float
    t_stat:       float
    p_value:      float
    cohens_d:     float
    significant:  bool

    def __str__(self) -> str:
        sig = "✓ SIGNIFICANT" if self.significant else "✗ not significant"
        return (
            f"\n  {self.metric}\n"
            f"    Control:    {self.mean_control:.3f}  (n={self.n_control:,})\n"
            f"    Treatment:  {self.mean_treatment:.3f}  (n={self.n_treatment:,})\n"
            f"    Lift:       {self.lift_abs:+.3f}  ({self.lift_rel_pct:+.1f}% relative)\n"
            f"    95% CI:     [{self.ci_lower:+.3f}, {self.ci_upper:+.3f}]\n"
            f"    t={self.t_stat:.3f}  p={self.p_value:.4f}  Cohen's d={self.cohens_d:.3f}\n"
            f"    Decision:   {sig}"
        )


# ── Core statistical functions ────────────────────────────────────────────────

def two_proportion_z_test(
    metric: str,
    x_c: int, n_c: int,
    x_t: int, n_t: int,
) -> ProportionTestResult:
    """Two-sided two-proportion z-test with Wald confidence interval."""
    p_c = x_c / n_c
    p_t = x_t / n_t
    p_pool = (x_c + x_t) / (n_c + n_t)

    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z = (p_t - p_c) / se_pool if se_pool > 0 else 0.0
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # Wald CI on the difference
    se_diff = math.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    z_crit  = stats.norm.ppf(1 - ALPHA / 2)
    diff    = p_t - p_c
    ci_lo   = (diff - z_crit * se_diff) * 100
    ci_hi   = (diff + z_crit * se_diff) * 100

    h = 2 * math.asin(math.sqrt(p_t)) - 2 * math.asin(math.sqrt(p_c))

    return ProportionTestResult(
        metric=metric,
        p_control=p_c, p_treatment=p_t,
        n_control=n_c, n_treatment=n_t,
        lift_pp=diff * 100,
        lift_rel_pct=(diff / p_c) * 100 if p_c else 0.0,
        ci_lower=ci_lo, ci_upper=ci_hi,
        z_stat=z, p_value=p_value,
        cohens_h=abs(h),
        significant=p_value < ALPHA,
    )


def welch_t_test(
    metric: str,
    control: np.ndarray,
    treatment: np.ndarray,
) -> ContinuousTestResult:
    """Welch's t-test (unequal variance) with Cohen's d."""
    t, p = stats.ttest_ind(treatment, control, equal_var=False)
    m_c, m_t = control.mean(), treatment.mean()
    diff = m_t - m_c

    # Pooled std for Cohen's d
    pooled_std = math.sqrt((control.std(ddof=1) ** 2 + treatment.std(ddof=1) ** 2) / 2)
    d = diff / pooled_std if pooled_std else 0.0

    # 95% CI via scipy
    ci = stats.ttest_ind(treatment, control, equal_var=False)
    se = math.sqrt(control.var(ddof=1) / len(control) + treatment.var(ddof=1) / len(treatment))
    z_crit = stats.norm.ppf(1 - ALPHA / 2)
    ci_lo, ci_hi = diff - z_crit * se, diff + z_crit * se

    return ContinuousTestResult(
        metric=metric,
        mean_control=m_c, mean_treatment=m_t,
        n_control=len(control), n_treatment=len(treatment),
        lift_abs=diff,
        lift_rel_pct=(diff / m_c) * 100 if m_c else 0.0,
        ci_lower=ci_lo, ci_upper=ci_hi,
        t_stat=t, p_value=p,
        cohens_d=abs(d),
        significant=p < ALPHA,
    )


def check_srm(n_control: int, n_treatment: int, expected_split: float = 0.5) -> dict:
    """Chi-square goodness-of-fit test for sample ratio mismatch."""
    n_total   = n_control + n_treatment
    exp_c     = n_total * expected_split
    exp_t     = n_total * (1 - expected_split)
    chi2, p   = stats.chisquare([n_control, n_treatment], f_exp=[exp_c, exp_t])
    return {
        "n_control":   n_control,
        "n_treatment": n_treatment,
        "expected_split": f"{expected_split:.0%} / {1-expected_split:.0%}",
        "actual_split":   f"{n_control/n_total:.1%} / {n_treatment/n_total:.1%}",
        "chi2":  round(chi2, 4),
        "p_value": round(p, 4),
        "srm_detected": p < ALPHA,
    }


def post_hoc_power(cohens_h: float, n_per_group: int) -> float:
    """Post-hoc power for two-proportion test using normal approximation."""
    z_alpha = stats.norm.ppf(1 - ALPHA / 2)
    power   = stats.norm.cdf(abs(cohens_h) * math.sqrt(n_per_group / 2) - z_alpha)
    return round(power, 4)


def minimum_detectable_effect(n_per_group: int, power: float = 0.80) -> float:
    """MDE (Cohen's h) given sample size, alpha, and desired power."""
    z_alpha = stats.norm.ppf(1 - ALPHA / 2)
    z_beta  = stats.norm.ppf(power)
    return round((z_alpha + z_beta) / math.sqrt(n_per_group / 2), 4)


# ── Analysis runners ──────────────────────────────────────────────────────────

def run_novelty_check(events: pd.DataFrame) -> pd.DataFrame:
    """Week-by-week claim rate by variant to detect novelty decay."""
    weekly = (
        events.groupby(["week", "variant"])
        .agg(claim_rate=("made_claim", "mean"), n=("made_claim", "count"))
        .reset_index()
    )
    pivot = weekly.pivot(index="week", columns="variant", values="claim_rate")
    pivot["lift_pp"] = (pivot["treatment"] - pivot["control"]) * 100
    return pivot.round(4).reset_index()


def run_segment_analysis(events: pd.DataFrame, segment_col: str) -> pd.DataFrame:
    """Claim rate lift broken down by a user segment column."""
    rows = []
    for seg_val, grp in events.groupby(segment_col):
        c = grp[grp.variant == "control"]
        t = grp[grp.variant == "treatment"]
        if len(c) == 0 or len(t) == 0:
            continue
        result = two_proportion_z_test(
            metric=str(seg_val),
            x_c=c.made_claim.sum(), n_c=len(c),
            x_t=t.made_claim.sum(), n_t=len(t),
        )
        rows.append({
            "segment":      seg_val,
            "p_control":    round(result.p_control, 4),
            "p_treatment":  round(result.p_treatment, 4),
            "lift_pp":      round(result.lift_pp, 2),
            "p_value":      round(result.p_value, 4),
            "significant":  result.significant,
        })
    return pd.DataFrame(rows)


# ── Full report ───────────────────────────────────────────────────────────────

def run_full_analysis(con: duckdb.DuckDBPyConnection = None) -> None:
    if con is None:
        con = get_connection()

    assignments = con.execute("SELECT * FROM ab_assignments").df()
    events      = con.execute("SELECT * FROM ab_events").df()

    ctrl_events = events[events.variant == "control"]
    trt_events  = events[events.variant == "treatment"]

    # Aggregate to one row per user across all weeks
    user_agg = (
        events.groupby(["user_id", "variant", "user_type", "league_type"])
        .agg(
            made_claim_any = ("made_claim",  "max"),
            total_claims   = ("num_claims",  "sum"),
            set_lineup_any = ("set_lineup",  "max"),
            retained       = ("retained",    "min"),   # retained ALL weeks
        )
        .reset_index()
    )
    ctrl = user_agg[user_agg.variant == "control"]
    trt  = user_agg[user_agg.variant == "treatment"]

    sep = "─" * 60

    # ── Header ────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("  WAIVER WIRE AI RECOMMENDATION EXPERIMENT")
    print(f"  NFL Season 2023 | Weeks 3–10 | α = {ALPHA}")
    print(f"{'═'*60}")

    # ── SRM ───────────────────────────────────────────────────
    n_c = len(assignments[assignments.variant == "control"])
    n_t = len(assignments[assignments.variant == "treatment"])
    srm = check_srm(n_c, n_t)
    srm_flag = "✗ SRM DETECTED — results unreliable" if srm["srm_detected"] else "✓ No SRM detected"
    print(f"\n{sep}")
    print("  [1] SAMPLE RATIO MISMATCH CHECK")
    print(f"{sep}")
    print(f"    Expected split:  {srm['expected_split']}")
    print(f"    Actual split:    {srm['actual_split']}")
    print(f"    χ²={srm['chi2']}  p={srm['p_value']}")
    print(f"    Result:          {srm_flag}")

    # ── Primary metric ─────────────────────────────────────────
    print(f"\n{sep}")
    print("  [2] PRIMARY METRIC — Weekly Waiver Claim Rate")
    print(f"{sep}")
    primary = two_proportion_z_test(
        "Waiver Claim Rate (per user-week)",
        x_c=ctrl_events.made_claim.sum(), n_c=len(ctrl_events),
        x_t=trt_events.made_claim.sum(),  n_t=len(trt_events),
    )
    print(primary)

    # ── Secondary metrics ──────────────────────────────────────
    print(f"\n{sep}")
    print("  [3] SECONDARY METRICS")
    print(f"{sep}")

    # Claims per user (continuous)
    claims_c = ctrl["total_claims"].values.astype(float)
    claims_t = trt["total_claims"].values.astype(float)
    print(welch_t_test("Total Claims per User (8-week period)", claims_c, claims_t))

    # Lineup set rate (per user-week, same grain as claim rate)
    lineup = two_proportion_z_test(
        "Lineup Set Rate (per user-week)",
        x_c=ctrl_events.set_lineup.sum(), n_c=len(ctrl_events),
        x_t=trt_events.set_lineup.sum(),  n_t=len(trt_events),
    )
    print(lineup)

    # Retention (retained all 8 weeks)
    retention = two_proportion_z_test(
        "Full-Season Retention",
        x_c=ctrl["retained"].sum(), n_c=len(ctrl),
        x_t=trt["retained"].sum(),  n_t=len(trt),
    )
    print(retention)

    # ── Novelty effect ─────────────────────────────────────────
    print(f"\n{sep}")
    print("  [4] NOVELTY EFFECT CHECK — Week-by-Week Claim Rate Lift")
    print(f"{sep}")
    novelty = run_novelty_check(events)
    print(f"    {'Week':<6} {'Control':>10} {'Treatment':>12} {'Lift (pp)':>12}")
    print(f"    {'────':<6} {'───────':>10} {'─────────':>12} {'─────────':>12}")
    for _, row in novelty.iterrows():
        print(f"    {int(row.week):<6} {row.control:>10.1%} {row.treatment:>12.1%} {row.lift_pp:>+11.2f}pp")

    # ── Segment analysis ───────────────────────────────────────
    print(f"\n{sep}")
    print("  [5] SEGMENT ANALYSIS — Claim Rate Lift by User Type")
    print(f"{sep}")
    seg_type = run_segment_analysis(events, "user_type")
    _print_segment_table(seg_type)

    print(f"\n  Claim Rate Lift by League Type")
    seg_league = run_segment_analysis(events, "league_type")
    _print_segment_table(seg_league)

    # ── Power analysis ─────────────────────────────────────────
    n_per_group = min(len(ctrl_events), len(trt_events))
    power  = post_hoc_power(primary.cohens_h, n_per_group)
    mde    = minimum_detectable_effect(n_per_group)
    print(f"\n{sep}")
    print("  [6] POWER ANALYSIS")
    print(f"{sep}")
    print(f"    Sample size (per group):  {n_per_group:,} user-weeks")
    print(f"    Observed Cohen's h:       {primary.cohens_h:.4f}")
    print(f"    Post-hoc power:           {power:.1%}")
    print(f"    MDE at 80% power:         h = {mde:.4f}")
    print(f"\n{'═'*60}\n")


def _print_segment_table(df: pd.DataFrame) -> None:
    print(f"    {'Segment':<12} {'Control':>10} {'Treatment':>12} {'Lift':>9} {'p-value':>9} {'Sig':>5}")
    print(f"    {'───────':<12} {'───────':>10} {'─────────':>12} {'────':>9} {'───────':>9} {'───':>5}")
    for _, row in df.iterrows():
        sig = "✓" if row.significant else "✗"
        print(
            f"    {str(row.segment):<12} {row.p_control:>10.1%} {row.p_treatment:>12.1%}"
            f" {row.lift_pp:>+8.2f}pp {row.p_value:>9.4f} {sig:>5}"
        )


if __name__ == "__main__":
    run_full_analysis()
