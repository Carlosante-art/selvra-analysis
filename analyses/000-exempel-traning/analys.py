"""000 · Exempel: TIR på träningsdagar. Följer forregistrering.md exakt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from selvra_analysis.provenance import run_analysis
from selvra_analysis.stats import block_bootstrap_difference, daily_series

HERE = Path(__file__).resolve().parent
MIN_TRAINING_DAYS = 20
SMALLEST_EFFECT = 5.0
BLOCK, SEED = 7, 1


def estimate(days, outcome: str, block: int) -> dict:
    s = daily_series(days, "reading_date", [outcome, "had_training", "is_valid_day"])
    valid = s["is_valid_day"].eq(True)
    y = s[outcome].where(valid)
    exposed = s["had_training"].where(valid & s["had_training"].notna())
    return block_bootstrap_difference(y, exposed, block_length=block, seed=SEED).as_dict()


def verdict(low: float, high: float) -> str:
    if low > SMALLEST_EFFECT:
        return "tesen håller"
    if high < SMALLEST_EFFECT:
        return "tesen motbevisad"
    return "obestämt"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/selvra.duckdb")
    con = duckdb.connect(parser.parse_args().db, read_only=True)
    days = con.execute(
        "select reading_date, tir_pct, tir_pct_clean, is_valid_day, had_training "
        "from marts.mart_analysis_days").df()

    primary = estimate(days, "tir_pct", BLOCK)
    result = {
        "underlag_tillrackligt": primary["n_exposed"] >= MIN_TRAINING_DAYS,
        "primart": primary,
        "slutsats": verdict(primary["ci_low"], primary["ci_high"]),
        "kanslighet": {
            "block_3": estimate(days, "tir_pct", 3),
            "block_14": estimate(days, "tir_pct", 14),
            "utan_artefakter": estimate(days, "tir_pct_clean", BLOCK),
        },
    }
    path = run_analysis(HERE, con, result)
    p = primary
    print(f"TIR träningsdagar minus övriga: {p['estimate']:+.1f} procentenheter "
          f"(95 % CI {p['ci_low']:+.1f} till {p['ci_high']:+.1f}; "
          f"{p['n_exposed']} mot {p['n_comparison']} dagar) → {result['slutsats']}")
    print(json.dumps({k: (v["estimate"], v["ci_low"], v["ci_high"])
                      for k, v in result["kanslighet"].items()}, indent=1))
    print(f"Körning: {path.relative_to(HERE.parents[1])}")


if __name__ == "__main__":
    main()
