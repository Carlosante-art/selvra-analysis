"""Check the pipeline's CGM metrics against iglu, an independent reference implementation.

Two checks, each on exactly the readings the pipeline used:

  daily   every metric in fct_glucose_daily, every day. A value passes when it equals
          iglu's to the precision the pipeline publishes (0.1 points for time in range).
  events  every glycaemic event in int_glycaemic_events (consensus 2023 hypo/hyper events).
          The set of events, with their first and last reading, must be identical.

iglu: Broll et al., PLoS ONE 2021, https://github.com/irinagain/iglu

Without R installed, a stored iglu result is used instead, but only when the readings are
byte-for-byte the ones it was computed from (the synthetic demo data). Any other data
needs R and iglu.

Usage:
    python -m selvra_analysis.validate_iglu --db data/selvra.duckdb
    python -m selvra_analysis.validate_iglu --db data/selvra.duckdb --save-reference
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
import yaml

MGDL_PER_MMOL = 18.016
ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "validation" / "iglu"
REFERENCE_META = VALIDATION / "reference_synthetic.json"

# pipeline column -> (iglu column, factor from iglu to pipeline units, published precision)
DAILY = {
    "mean_mmol": ("mean_mgdl", 1 / MGDL_PER_MMOL, 0.01),
    "sd_mmol": ("sd_mgdl", 1 / MGDL_PER_MMOL, 0.01),
    "cv_pct": ("cv_pct", 1.0, 0.1),
    "gmi_pct": ("gmi_pct", 1.0, 0.01),
    "tir_pct": ("tir_pct", 1.0, 0.1),
    "tar_pct": ("tar_pct", 1.0, 0.1),
    "tar_level2_pct": ("tar_level2_pct", 1.0, 0.1),
    "tbr_pct": ("tbr_pct", 1.0, 0.1),
    "tbr_level2_pct": ("tbr_level2_pct", 1.0, 0.1),
    "mean_mmol_clean": ("mean_mgdl_clean", 1 / MGDL_PER_MMOL, 0.01),
    "tir_pct_clean": ("tir_pct_clean", 1.0, 0.1),
    "tbr_pct_clean": ("tbr_pct_clean", 1.0, 0.1),
}
EVENT_KEY = ["event_type", "segment_id", "start_rn", "last_rn"]


def dbt_vars() -> dict:
    return yaml.safe_load((ROOT / "transform" / "dbt_project.yml").read_text())["vars"]


def thresholds_mgdl(v: dict) -> dict:
    return {
        "low": v["range_low_mmol"] * MGDL_PER_MMOL,
        "high": v["range_high_mmol"] * MGDL_PER_MMOL,
        "low2": v["level2_low_mmol"] * MGDL_PER_MMOL,
        "high2": v["level2_high_mmol"] * MGDL_PER_MMOL,
    }


def write_csv(df: pd.DataFrame, path: Path) -> str:
    df.to_csv(path, index=False, float_format="%.10g")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_daily(con, path: Path, v: dict) -> str:
    df = con.execute(
        """
        select
            strftime(reading_date, '%Y-%m-%d')                         as id,
            strftime(timezone('UTC', reading_at), '%Y-%m-%dT%H:%M:%S') as time,
            glucose_mmol * $f                                          as gl,
            case when flag_compression_low or flag_implausible_jump
                 then 'true' else 'false' end                          as is_artefact
        from intermediate.int_cgm_flagged
        order by reading_at, reading_id
        """,
        {"f": MGDL_PER_MMOL},
    ).df()
    for name, value in thresholds_mgdl(v).items():
        df[name] = value
    return write_csv(df, path)


def export_events(con, path: Path, v: dict) -> str:
    df = con.execute(
        """
        select
            segment_id,
            row_number() over (partition by segment_id order by reading_at, reading_id) as rn,
            glucose_mmol * $f as gl
        from intermediate.int_cgm_flagged
        order by segment_id, rn
        """,
        {"f": MGDL_PER_MMOL},
    ).df()
    step = v["cgm_interval_minutes"]
    for name, value in thresholds_mgdl(v).items():
        df[name] = value
    df["n_min"] = math.ceil(v["event_min_minutes"] / step)
    df["n_end"] = math.ceil(v["event_end_minutes"] / step)
    df["n_ext"] = v["extended_hypo_minutes"] // step + 1
    return write_csv(df, path)


def compare_daily(pipeline: pd.DataFrame, iglu: pd.DataFrame) -> list[str]:
    iglu = iglu.add_prefix("iglu_").rename(columns={"iglu_id": "id"})
    merged = pipeline.merge(iglu, left_on="reading_date", right_on="id", how="outer", indicator=True)
    problems = [f"day present on one side only: {r.reading_date or r.id}"
                for r in merged[merged["_merge"] != "both"].itertuples()]
    both = merged[merged["_merge"] == "both"]
    for col, (icol, factor, precision) in DAILY.items():
        ours = both[col].astype(float)
        ref = both["iglu_" + icol].astype(float) * factor
        # A value rounded to `precision` is within half a unit of the exact one (plus float noise).
        bad = ((ours - ref).abs() > precision / 2 + 1e-9) | (ours.isna() != ref.isna())
        for day, o, r in zip(both.loc[bad, "reading_date"], ours[bad], ref[bad], strict=True):
            problems.append(f"{day} {col}: pipeline {o}, iglu {r:.4f}")
    return problems


def compare_events(pipeline: pd.DataFrame, iglu: pd.DataFrame) -> list[str]:
    def keys(df: pd.DataFrame) -> set[tuple]:
        return {(t, int(s), int(a), int(b)) for t, s, a, b in df[EVENT_KEY].itertuples(index=False)}

    ours, ref = keys(pipeline), keys(iglu)
    return ([f"only in pipeline: {e}" for e in sorted(ours - ref)]
            + [f"only in iglu: {e}" for e in sorted(ref - ours)])


def run_r(script: str, inp: Path, out: Path) -> None:
    rscript = shutil.which("Rscript")
    if rscript is None:
        raise FileNotFoundError("Rscript")
    # Fixed R scripts from this repo on files this process just wrote; no user input.
    subprocess.run([rscript, str(VALIDATION / script), str(inp), str(out)], check=True)  # noqa: S603


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "selvra.duckdb")
    parser.add_argument("--save-reference", action="store_true",
                        help="store iglu's results as the reference for the synthetic demo data")
    args = parser.parse_args(argv)

    v = dbt_vars()
    con = duckdb.connect(str(args.db), read_only=True)
    con.execute("set TimeZone = 'UTC'")
    daily = con.execute("select * from marts.fct_glucose_daily").df()
    daily["reading_date"] = daily["reading_date"].astype(str)
    columns = ", ".join(EVENT_KEY)  # a module constant, not input
    events = con.execute(f"select {columns} from intermediate.int_glycaemic_events").df()  # noqa: S608

    checks = {
        "daily": ("iglu_daily.R", export_daily, compare_daily, daily, f"{len(daily) * len(DAILY)} values"),
        "events": ("iglu_events.R", export_events, compare_events, events, f"{len(events)} events"),
    }
    meta = json.loads(REFERENCE_META.read_text()) if REFERENCE_META.exists() else {}
    new_meta: dict = {}
    failed = False

    with tempfile.TemporaryDirectory() as tmp:
        for name, (script, export, compare, ours, size) in checks.items():
            inp, out = Path(tmp) / f"{name}_in.csv", Path(tmp) / f"{name}_iglu.csv"
            digest = export(con, inp, v)
            stored = VALIDATION / f"reference_synthetic_{name}.csv"
            try:
                run_r(script, inp, out)
                source = "live"
            except FileNotFoundError:
                if meta.get(name, {}).get("input_sha256") != digest:
                    print(f"{name}: Rscript not found, and these readings are not the synthetic demo data "
                          "the stored reference was computed from. Install R and iglu to validate them.")
                    return 2
                out, source = stored, "stored reference"
            ref = pd.read_csv(out, dtype={"id": str})
            version = ref["iglu_version"].iloc[0] if len(ref) else meta.get(name, {}).get("iglu_version", "?")
            problems = compare(ours, ref)
            if problems:
                failed = True
                print(f"{name}: MISMATCH against iglu {version} ({source}), {len(problems)} differences")
                print("\n".join("  " + p for p in problems[:40]))
            else:
                print(f"{name}: OK, {size} identical to iglu {version} ({source})")
            if args.save_reference:
                shutil.copy(out, stored)
                new_meta[name] = {"input_sha256": digest, "iglu_version": str(version), "rows": len(ref)}

    if args.save_reference:
        REFERENCE_META.write_text(json.dumps(new_meta, indent=2) + "\n")
        print(f"Saved references to {VALIDATION.relative_to(ROOT)}/")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
