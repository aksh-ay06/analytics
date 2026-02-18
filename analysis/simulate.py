"""
Simulates a Sleeper A/B experiment and stores results in DuckDB.

Experiment hypothesis:
  Showing AI-powered waiver wire recommendations increases the weekly
  waiver claim rate, driving higher engagement and retention.

  Control   — standard waiver wire UI
  Treatment — waiver wire + AI player recommendations

10,000 users | NFL 2023 season weeks 3-10 (8 weeks)
"""

import numpy as np
import pandas as pd
import duckdb
from pipeline.ingest import get_connection

SEED = 42
N_USERS = 10_000
SEASON = 2023
EXPERIMENT_WEEKS = list(range(3, 11))  # weeks 3-10

# Per-week waiver claim probability by (user_type, variant)
CLAIM_RATE = {
    ("returning", "control"):   0.35,
    ("returning", "treatment"): 0.43,
    ("new",       "control"):   0.25,
    ("new",       "treatment"): 0.31,
}

# Poisson lambda for number of claims, given user made at least one
CLAIMS_PER_CLAIMER = {
    "control":   1.8,
    "treatment": 2.2,
}

# Probability of setting lineup before game-time lock
LINEUP_SET_RATE = {
    "control":   0.82,
    "treatment": 0.86,
}

# Probability of returning the following week
RETENTION_RATE = {
    ("returning", "control"):   0.80,
    ("returning", "treatment"): 0.83,
    ("new",       "control"):   0.65,
    ("new",       "treatment"): 0.69,
}

# Novelty effect: treatment lift decays slightly over first 3 weeks
NOVELTY_DECAY = {3: 0.04, 4: 0.02, 5: 0.01}


def simulate_assignments(rng: np.random.Generator) -> pd.DataFrame:
    """One row per user: assignment + static attributes."""
    user_ids  = np.arange(1, N_USERS + 1)
    variants  = rng.choice(["control", "treatment"], size=N_USERS, p=[0.5, 0.5])
    user_types = rng.choice(
        ["new", "returning"], size=N_USERS, p=[0.20, 0.80]
    )
    league_types = rng.choice(
        ["standard", "ppr", "dynasty"], size=N_USERS, p=[0.55, 0.35, 0.10]
    )
    return pd.DataFrame({
        "user_id":     user_ids,
        "variant":     variants,
        "user_type":   user_types,
        "league_type": league_types,
        "season":      SEASON,
        "start_week":  EXPERIMENT_WEEKS[0],
    })


def simulate_events(
    assignments: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """One row per (user, week): engagement outcomes."""
    records = []

    for week in EXPERIMENT_WEEKS:
        novelty_boost = NOVELTY_DECAY.get(week, 0.0)

        for _, user in assignments.iterrows():
            key_type    = (user.user_type, user.variant)
            base_rate   = CLAIM_RATE[key_type]
            claim_prob  = min(base_rate + novelty_boost, 1.0)

            made_claim  = int(rng.binomial(1, claim_prob))
            num_claims  = (
                int(rng.poisson(CLAIMS_PER_CLAIMER[user.variant]))
                if made_claim else 0
            )
            set_lineup  = int(rng.binomial(1, LINEUP_SET_RATE[user.variant]))
            retained    = int(rng.binomial(1, RETENTION_RATE[key_type]))

            records.append({
                "user_id":        user.user_id,
                "variant":        user.variant,
                "user_type":      user.user_type,
                "league_type":    user.league_type,
                "season":         SEASON,
                "week":           week,
                "made_claim":     made_claim,
                "num_claims":     num_claims,
                "set_lineup":     set_lineup,
                "retained":       retained,
            })

    return pd.DataFrame(records)


def run_simulation(con: duckdb.DuckDBPyConnection = None) -> duckdb.DuckDBPyConnection:
    if con is None:
        con = get_connection()

    rng = np.random.default_rng(SEED)
    print("Simulating experiment assignments...")
    assignments = simulate_assignments(rng)
    con.execute("DROP TABLE IF EXISTS ab_assignments")
    con.execute("CREATE TABLE ab_assignments AS SELECT * FROM assignments")
    print(f"  {len(assignments):,} users assigned (control / treatment: "
          f"{(assignments.variant=='control').sum()} / "
          f"{(assignments.variant=='treatment').sum()})")

    print("Simulating weekly experiment events...")
    events = simulate_events(assignments, rng)
    con.execute("DROP TABLE IF EXISTS ab_events")
    con.execute("CREATE TABLE ab_events AS SELECT * FROM events")
    print(f"  {len(events):,} user-week records generated")

    return con


if __name__ == "__main__":
    run_simulation()
