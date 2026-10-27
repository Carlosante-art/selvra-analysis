"""Reproduce a locked study's result: same code + same data must give the same numbers.

Recomputes the example study's primary and negative-control estimates on the synthetic
demo database and compares them with a stored reference, value by value. Nothing is
written to the study folder, so the study itself is not spent.

Counts, flags and the data version must match exactly. Floating-point values must match to
a relative 1e-9: DuckDB sums in parallel, and the order of a floating-point sum depends on
the number of threads, so the last bits differ between a laptop and a CI runner.

    python -m selvra_analysis.reproduce --db data/demo.duckdb
    python -m selvra_analysis.reproduce --db data/demo.duckdb --save   # after an intended change
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import duckdb

from selvra_analysis import study as st
from selvra_analysis.provenance import ROOT, data_version

STUDY = ROOT / "studies" / "000-exempel-promenad" / "studie.yml"
REL_TOL = 1e-9
REFERENCE = ROOT / "validation" / "reproduce" / "000-exempel-promenad.json"


def compute(db: Path) -> dict:
    study = st.load(STUDY)
    with duckdb.connect(str(db), read_only=True) as con:
        primary, _ = st._estimate(study, con, study.spec["utfall"])
        negative, _ = st._estimate(study, con, study.spec["negativ_kontroll"])
        return {"data_fingerprint": data_version(con)["fingerprint"],
                "primary": primary, "negative_control": negative}


def differences(now: dict, ref: dict) -> list[str]:
    out = []
    if now["data_fingerprint"] != ref["data_fingerprint"]:
        out.append("the demo data differs from the data the reference was made on")
    for part in ("primary", "negative_control"):
        for key, value in ref[part].items():
            new = now[part].get(key)
            same = new == value
            if isinstance(value, float) and isinstance(new, float):
                same = (math.isnan(value) and math.isnan(new)) or math.isclose(
                    new, value, rel_tol=REL_TOL, abs_tol=1e-12)
            if not same:
                out.append(f"{part}.{key}: reference {value}, now {new}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "demo.duckdb")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args(argv)
    now = compute(args.db)
    if args.save:
        REFERENCE.write_text(json.dumps(now, indent=2, default=str) + "\n")
        print(f"Saved {REFERENCE.relative_to(ROOT)}")
        return 0
    diffs = differences(now, json.loads(REFERENCE.read_text()))
    if diffs:
        print("NOT REPRODUCED:\n  " + "\n  ".join(diffs))
        if os.environ.get("GITHUB_ACTIONS"):  # visible as annotations on the run
            for d in diffs:
                print(f"::error title=Not reproduced::{d}")
        return 1
    print(f"Reproduced: {len(now['primary']) + len(now['negative_control'])} values match the stored "
          f"result (exact for counts, relative {REL_TOL:g} for floating point).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
