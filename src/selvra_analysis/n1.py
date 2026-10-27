r"""N-of-1 experiments: randomised schedule, randomisation test, power.

Design: paired periods. Every pair holds one period of each condition (A = intervention,
B = comparison) in random order, decided by a coin flip per pair before the experiment
starts. Pairing balances slow drift (season, sensor age, stress) across the conditions;
randomising the order inside each pair is what allows a causal claim.

Analysis: the randomisation test (Edgington & Onghena 2007). Under the null hypothesis
that the condition makes no difference on any period, swapping the labels inside a pair
would have given the same data, so the 2^n ways the coins could have fallen give the
exact distribution of the effect estimate under the null. No assumption of normality or
independent days is needed: the test follows the randomisation that was actually done.
The confidence interval is every constant effect the test does not reject.

Carryover: each period can start with washout days that are excluded from the outcome
(analytic washout). Order effects are reported separately for AB and BA pairs.

    python -m selvra_analysis.n1 schedule --start 2026-11-02 --pairs 8 --period-days 2 \
        --washout-days 1 --out analyses/NNN-namn/schema.csv
    python -m selvra_analysis.n1 power --pairs 8 --effect 5 --sd 8
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import secrets
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

EXACT_MAX_PAIRS = 16


# --- Schedule ---------------------------------------------------------------------------------

WEEKDAYS = {"mandag": 0, "tisdag": 1, "onsdag": 2, "torsdag": 3, "fredag": 4, "lordag": 5, "sondag": 6}


def eligible_dates(start: date, n_needed: int, weekdays: list[str] | None = None,
                   dates: list[date] | None = None, min_gap: int = 1) -> list[date]:
    """The first n_needed days from start on which both conditions are possible.

    Restricted randomisation (Edgington & Onghena): when a condition is impossible or
    confounded on some days (B = few steps on a work day), randomise only among days
    where both are possible. Pairs are formed from consecutive eligible days, so the
    paired randomisation test stays valid; the result applies to those days only.

    min_gap: fewest calendar days between two chosen days. Days off in a rotating schedule
    come in clusters; a day closer than min_gap to the previous chosen day is skipped, so an
    effect that lasts (exercise: 24-48 h) does not reach the next analysed day. The choice
    depends only on the calendar, never on outcomes, and is made before randomisation.
    """
    if dates is not None:
        pool = sorted(d for d in dates if d >= start)
    else:
        wanted = {WEEKDAYS[w] for w in weekdays or []}
        if not wanted:
            raise ValueError("give weekdays or dates")
        pool = (start + timedelta(days=i) for i in itertools.count())
        pool = (d for d in pool if d.weekday() in wanted)
    out: list[date] = []
    for d in pool:
        if not out or (d - out[-1]).days >= min_gap:
            out.append(d)
            if len(out) == n_needed:
                return out
    raise ValueError(f"need {n_needed} eligible dates from {start} at least {min_gap} days apart, got {len(out)}")


def make_schedule(start: date, n_pairs: int, period_days: int, washout_days: int, seed: int,
                  days: list[date] | None = None) -> pd.DataFrame:
    """One row per day: pair, period, condition (A/B), and whether the day is washout.

    With `days` (eligible dates, see eligible_dates) each period is one eligible day and each
    pair two consecutive eligible days; otherwise periods run on consecutive calendar days.
    """
    if not 0 <= washout_days < period_days:
        raise ValueError("washout_days must be at least 0 and less than period_days")
    rng = np.random.default_rng(seed)
    if days is not None:
        if period_days != 1 or washout_days != 0:
            raise ValueError("eligible-day schedules use one-day periods without washout")
        rows = []
        for pair in range(1, n_pairs + 1):
            order = ("A", "B") if rng.random() < 0.5 else ("B", "A")
            for k, condition in enumerate(order):
                rows.append({"date": days[2 * (pair - 1) + k], "pair": pair, "period": 2 * (pair - 1) + k + 1,
                             "condition": condition, "order": "".join(order), "washout": False})
        return pd.DataFrame(rows)
    rows = []
    day = start
    for pair in range(1, n_pairs + 1):
        order = ("A", "B") if rng.random() < 0.5 else ("B", "A")
        for k, condition in enumerate(order):
            period = 2 * (pair - 1) + k + 1
            for d in range(period_days):
                rows.append({"date": day, "pair": pair, "period": period, "condition": condition,
                             "order": "".join(order), "washout": d < washout_days})
                day += timedelta(days=1)
    return pd.DataFrame(rows)


def write_schedule(schedule: pd.DataFrame, path: Path, seed: int) -> str:
    """Write the schedule and return its SHA-256, to be quoted in the pre-registration."""
    text = f"# seed={seed}\n" + schedule.to_csv(index=False)
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def read_schedule(path: Path) -> pd.DataFrame:
    s = pd.read_csv(path, comment="#", parse_dates=["date"])
    s["date"] = s["date"].dt.date
    return s


# --- Period outcomes --------------------------------------------------------------------------

def period_outcomes(schedule: pd.DataFrame, daily: pd.DataFrame, outcome: str,
                    date_column: str = "reading_date", valid_column: str | None = "is_valid_day") -> pd.DataFrame:
    """Mean of `outcome` over each period's non-washout days that have a valid value."""
    d = daily[[date_column, outcome] + ([valid_column] if valid_column else [])].copy()
    d[date_column] = pd.to_datetime(d[date_column]).dt.date
    if valid_column:
        d.loc[d[valid_column] != True, outcome] = np.nan
    m = schedule[~schedule["washout"]].merge(d, left_on="date", right_on=date_column, how="left")
    return (m.groupby(["pair", "period", "condition", "order"], as_index=False)
             .agg(value=(outcome, "mean"), n_days=(outcome, "count")))


# --- Randomisation test -----------------------------------------------------------------------

@dataclass(frozen=True)
class N1Result:
    estimate: float          # mean over pairs of (A - B)
    ci_low: float
    ci_high: float
    p_value: float           # two-sided randomisation test of no effect
    level: float
    n_pairs: int
    n_pairs_dropped: int     # pairs with a period without valid data
    exact: bool              # all 2^n assignments enumerated (else Monte Carlo)
    min_attainable_p: float  # smallest p-value this number of pairs can give
    estimate_ab_pairs: float  # order effect check: pairs run A then B
    estimate_ba_pairs: float  # pairs run B then A
    method: str = "paired randomisation test, CI by test inversion"

    def as_dict(self) -> dict:
        return asdict(self)


def _signs(n: int, n_mc: int, rng: np.random.Generator) -> tuple[np.ndarray, bool]:
    if n <= EXACT_MAX_PAIRS:
        return np.array(list(itertools.product((1.0, -1.0), repeat=n))), True
    return rng.choice((1.0, -1.0), size=(n_mc, n)), False


def _p_value(diffs: np.ndarray, signs: np.ndarray, exact: bool) -> float:
    observed = abs(diffs.mean())
    null = np.abs((signs * diffs).mean(axis=1))
    hits = np.sum(null >= observed - 1e-12)
    return hits / len(signs) if exact else (hits + 1) / (len(signs) + 1)


def _bound(diffs, signs, exact, alpha, inside: float, outside: float) -> float:
    """Bisect between a shift the test does not reject and one it rejects."""
    for _ in range(60):
        mid = (inside + outside) / 2
        if _p_value(diffs - mid, signs, exact) > alpha:
            inside = mid
        else:
            outside = mid
    return inside


def randomisation_test(periods: pd.DataFrame, level: float = 0.95, seed: int = 0,
                       n_mc: int = 100_000) -> N1Result:
    """Analyse period outcomes from period_outcomes(): columns pair, condition, order, value."""
    wide = periods.pivot_table(index=["pair", "order"], columns="condition", values="value").reset_index()
    complete = wide.dropna(subset=["A", "B"])
    n_dropped = len(wide) - len(complete)
    diffs = (complete["A"] - complete["B"]).to_numpy(dtype=float)
    n = len(diffs)
    if n < 2:
        raise ValueError("need at least two complete pairs")

    signs, exact = _signs(n, n_mc, np.random.default_rng(seed))
    alpha = 1 - level
    est = float(diffs.mean())
    p = _p_value(diffs, signs, exact)
    spread = float(np.abs(diffs).max() * 4 + 1)
    low, high = -np.inf, np.inf  # unbounded where no shift can be rejected (too few pairs)
    if _p_value(diffs - (est - spread), signs, exact) <= alpha:
        low = _bound(diffs, signs, exact, alpha, est, est - spread)
    if _p_value(diffs - (est + spread), signs, exact) <= alpha:
        high = _bound(diffs, signs, exact, alpha, est, est + spread)

    order = complete["order"].to_numpy()
    return N1Result(
        estimate=est, ci_low=float(low), ci_high=float(high), p_value=float(p), level=level,
        n_pairs=n, n_pairs_dropped=int(n_dropped), exact=exact,
        min_attainable_p=2 / 2**n,
        estimate_ab_pairs=float(diffs[order == "AB"].mean()) if (order == "AB").any() else float("nan"),
        estimate_ba_pairs=float(diffs[order == "BA"].mean()) if (order == "BA").any() else float("nan"),
    )


# --- Power ------------------------------------------------------------------------------------

def power(n_pairs: int, effect: float, sd: float, alpha: float = 0.05, n_sim: int = 2000,
          seed: int = 0) -> float:
    """Share of simulated experiments where the randomisation test rejects at `alpha`.

    effect: true difference A - B in the outcome's unit. sd: standard deviation of one period's
    outcome around its condition mean. Estimate sd from existing data: the SD of the outcome
    averaged over blocks of days as long as the analysed part of a period.
    """
    rng = np.random.default_rng(seed)
    signs, exact = _signs(n_pairs, 20_000, rng)
    rejected = 0
    for _ in range(n_sim):
        a = rng.normal(effect, sd, n_pairs)
        b = rng.normal(0.0, sd, n_pairs)
        rejected += _p_value(a - b, signs, exact) <= alpha
    return rejected / n_sim


def window_outcomes(con, start: str, end: str, min_coverage_pct: float = 70.0) -> pd.DataFrame:
    """Daily glucose metrics in a fixed local-time window, e.g. "18:00" to "21:00".

    An outcome close to the intervention's mechanism (the hours after an evening walk)
    is usually far less noisy than a whole-day metric, which can decide whether an
    experiment of realistic length can answer the question at all.
    """
    return con.execute(
        """
        with w as (
            select reading_date, glucose_mmol,
                   flag_compression_low or flag_implausible_jump as is_artefact
            from intermediate.int_cgm_flagged
            where cast(reading_at_local as time) >= cast($start as time)
              and cast(reading_at_local as time) <  cast($end as time)
        )
        select
            reading_date,
            count(*)                                                     as n_readings,
            avg(glucose_mmol)                                            as mean_mmol,
            max(glucose_mmol)                                            as peak_mmol,
            100.0 * avg(case when glucose_mmol > 10.0 then 1 else 0 end) as tar_pct,
            bool_or(is_artefact)                                         as has_artefact,
            100.0 * count(*) / (date_diff('minute', cast($start as time), cast($end as time)) / 5)
                >= $cov                                                  as is_valid_day
        from w
        group by reading_date
        order by reading_date
        """,
        {"start": start, "end": end, "cov": min_coverage_pct},
    ).df()


def period_sd(daily: pd.DataFrame, outcome: str, analysed_days: int,
              date_column: str = "reading_date", valid_column: str | None = "is_valid_day") -> float:
    """SD of the outcome averaged over consecutive non-overlapping blocks of `analysed_days`
    days, from data you already have. Blocks with an invalid day are left out. This is the
    `sd` that power() needs, measured on your own variability before the experiment."""
    d = daily.copy()
    d[date_column] = pd.to_datetime(d[date_column])
    d = d.set_index(date_column).sort_index()
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="D"))
    y = d[outcome].where(d[valid_column] == True) if valid_column else d[outcome]
    block = np.arange(len(y)) // analysed_days
    means = y.groupby(block).agg(["mean", "count"])
    return float(means.loc[means["count"] == analysed_days, "mean"].std(ddof=1))


# --- CLI --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("schedule", help="draw the randomised schedule")
    s.add_argument("--start", type=date.fromisoformat, required=True)
    s.add_argument("--pairs", type=int, required=True)
    s.add_argument("--period-days", type=int, required=True)
    s.add_argument("--washout-days", type=int, default=0)
    s.add_argument("--seed", type=int, help="default: drawn from the OS's random source and recorded")
    s.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("power", help="power of the randomisation test by simulation")
    p.add_argument("--pairs", type=int, required=True)
    p.add_argument("--effect", type=float, required=True)
    p.add_argument("--sd", type=float, required=True)
    p.add_argument("--alpha", type=float, default=0.05)
    v = sub.add_parser("sd", help="period SD of an outcome from existing data, for power")
    v.add_argument("--db", type=Path, default=Path("data/selvra.duckdb"))
    v.add_argument("--outcome", required=True, help="column in marts.mart_analysis_days")
    v.add_argument("--days", type=int, required=True, help="analysed days per period")
    v.add_argument("--window", nargs=2, metavar=("START", "END"),
                   help="use a local-time window instead, e.g. 18:00 21:00; outcome is then "
                        "mean_mmol, peak_mmol or tar_pct")
    args = parser.parse_args(argv)

    if args.cmd == "schedule":
        seed = args.seed if args.seed is not None else secrets.randbits(32)
        sched = make_schedule(args.start, args.pairs, args.period_days, args.washout_days, seed)
        digest = write_schedule(sched, args.out, seed)
        orders = sched.drop_duplicates("pair")["order"].value_counts().to_dict()
        print(f"Wrote {args.out}: {args.pairs} pairs, {len(sched)} days, "
              f"{sched['date'].min()} to {sched['date'].max()}, orders {orders}")
        print(f"Quote in the pre-registration:  **Schema:** `{args.out.name}` sha256 `{digest}`")
    elif args.cmd == "sd":
        with duckdb.connect(str(args.db), read_only=True) as con:
            if args.window:
                daily = window_outcomes(con, *args.window)
            else:
                columns = {r[0] for r in con.execute(
                    "select column_name from information_schema.columns "
                    "where table_schema = 'marts' and table_name = 'mart_analysis_days'").fetchall()}
                if args.outcome not in columns:
                    raise SystemExit(f"{args.outcome!r} is not a column of marts.mart_analysis_days")
                # The column name is checked against the table above, so interpolating it is safe.
                daily = con.execute(f'select reading_date, "{args.outcome}", is_valid_day '  # noqa: S608
                                    'from marts.mart_analysis_days').df()
        sd = period_sd(daily, args.outcome, args.days)
        print(f"SD of {args.outcome} over {args.days}-day blocks: {sd:.2f}")
    else:
        pw = power(args.pairs, args.effect, args.sd, args.alpha)
        print(f"{args.pairs} pairs, effect {args.effect}, period SD {args.sd}: power {pw:.0%} "
              f"at alpha {args.alpha} (smallest attainable p {2 / 2**args.pairs:.4f})")


if __name__ == "__main__":
    main()
