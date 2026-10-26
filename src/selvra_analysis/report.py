"""Descriptive period report: what the last N days looked like, by the consensus metrics.

This answers questions like "how has my glucose been the last 30 days?". It describes;
it does not test anything. Questions about causes or differences are studies
(studies/README.md).

Metrics are computed over all readings in the period (not as an average of daily
percentages), as in the consensus (Battelino et al., Diabetes Care 2019;42:1593) and the
AGP report. Hypo/hyper events follow Battelino et al., Lancet Diabetes Endocrinol 2023.
The previous period of equal length is shown beside it, as description only.

    python -m selvra_analysis.report --dagar 30 --db data/selvra.duckdb
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

from selvra_analysis.provenance import ROOT, data_version

MGDL = 18.016

# Consensus targets for most adults with type 1 diabetes (Battelino et al. 2019)
TARGETS = {
    "tir_pct": (">", 70.0), "tbr_pct": ("<", 4.0), "tbr_level2_pct": ("<", 1.0),
    "tar_pct": ("<", 25.0), "tar_level2_pct": ("<", 5.0), "cv_pct": ("≤", 36.0),
}
LABELS = {
    "tir_pct": "Tid i målområdet 3,9–10,0", "tbr_pct": "Tid under 3,9", "tbr_level2_pct": "Tid under 3,0",
    "tar_pct": "Tid över 10,0", "tar_level2_pct": "Tid över 13,9", "mean_mmol": "Medelglukos",
    "gmi_pct": "GMI (skattat HbA1c)", "cv_pct": "Variationskoefficient (CV)",
    "tbr_pct_clean": "Tid under 3,9 utan artefakter",
}
UNITS = {"mean_mmol": "mmol/L", "gmi_pct": "%"}


def period_metrics(con, start: date, end: date) -> dict:
    """Consensus metrics over all readings with start <= local date <= end."""
    r = con.execute(
        """
        select
            count(*)                                                                  as n,
            avg(glucose_mmol)                                                         as mean_mmol,
            100 * stddev_samp(glucose_mmol) / avg(glucose_mmol)                       as cv_pct,
            100 * avg(case when glucose_mmol between 3.9 and 10.0 then 1 else 0 end)  as tir_pct,
            100 * avg(case when glucose_mmol < 3.9 then 1 else 0 end)                 as tbr_pct,
            100 * avg(case when glucose_mmol < 3.0 then 1 else 0 end)                 as tbr_level2_pct,
            100 * avg(case when glucose_mmol > 10.0 then 1 else 0 end)                as tar_pct,
            100 * avg(case when glucose_mmol > 13.9 then 1 else 0 end)                as tar_level2_pct,
            100 * avg(case when glucose_mmol < 3.9 then 1 else 0 end)
                filter (where not (flag_compression_low or flag_implausible_jump))     as tbr_pct_clean,
            count(distinct reading_date)                                              as days_with_data,
            min(reading_at_local) as first_local, max(reading_at_local) as last_local
        from intermediate.int_cgm_flagged
        where reading_date between ? and ?
        """,
        [start, end],
    ).df().iloc[0].to_dict()
    expected = con.execute(
        "select sum(n_expected) from marts.fct_glucose_daily where reading_date between ? and ?",
        [start, end]).fetchone()[0]
    n_days = (end - start).days + 1
    # Days without any reading are missing from fct_glucose_daily; count them as 288 expected.
    covered = con.execute("select count(*) from marts.fct_glucose_daily where reading_date between ? and ?",
                          [start, end]).fetchone()[0]
    expected = (expected or 0) + 288 * (n_days - covered)
    r["coverage_pct"] = 100 * r["n"] / expected if r["n"] else 0.0
    r["gmi_pct"] = 3.31 + 0.02392 * r["mean_mmol"] * MGDL if r["n"] else None
    events = con.execute(
        "select event_type, count(*) as n, count(*) filter (where not contains_artefact) as n_clean "
        "from intermediate.int_glycaemic_events where start_date between ? and ? group by 1",
        [start, end]).df().set_index("event_type")
    for t in ("hypo_level1", "hypo_level2", "hypo_extended", "hyper_level1", "hyper_level2"):
        r[f"n_{t}"] = int(events["n"].get(t, 0))
        r[f"n_{t}_clean"] = int(events["n_clean"].get(t, 0))
    r["n_days"] = n_days
    return r


def _num(v, digits=1) -> str:
    return "–" if v is None or math.isnan(v) else f"{v:.{digits}f}".replace(".", ",")


def render(cur: dict, prev: dict, start: date, end: date, data: dict) -> str:
    sufficient = cur["n_days"] >= 14 and cur["coverage_pct"] >= 70
    lines = [
        f"# Glukos {start} – {end}", "",
        (f"*{cur['n_days']} dagar · {cur['n']} mätningar · täckning {_num(cur['coverage_pct'], 0)} % · "
         f"dataversion `{data['fingerprint'][:12]}`*"), "",
    ]
    if data["synthetic"]:
        lines += ["> **Syntetisk demodata.** Siffrorna beskriver inte en verklig person.", ""]
    if not sufficient:
        lines += [("> Under konsensuskravet (minst 14 dagar med minst 70 % täckning). Måtten beskriver "
                   "perioden men representerar inte en typisk period."), ""]
    lines += [
        "| Mått | Perioden | Föregående period | Konsensusmål | Inom mål |",
        "|---|---|---|---|---|",
    ]
    for key in ("tir_pct", "tbr_pct", "tbr_level2_pct", "tar_pct", "tar_level2_pct",
                "mean_mmol", "gmi_pct", "cv_pct"):
        unit = UNITS.get(key, "%")
        target = TARGETS.get(key)
        within = ""
        if target and cur.get(key) is not None:
            op, val = target
            ok = cur[key] > val if op == ">" else (cur[key] < val if op == "<" else cur[key] <= val)
            within = "ja" if ok else "nej"
        tgt = f"{target[0]} {_num(target[1], 0)} %" if target else ""
        lines.append(f"| {LABELS[key]} | {_num(cur.get(key))} {unit} | {_num(prev.get(key))} {unit} | {tgt} | {within} |")
    lines += [
        "", "## Händelser (konsensus 2023)", "",
        "| | Antal | Varav utan artefakt | Föregående period |", "|---|---|---|---|",
    ]
    for t, label in (("hypo_level1", "Hypo nivå 1 (< 3,9 i ≥ 15 min)"), ("hypo_level2", "Hypo nivå 2 (< 3,0 i ≥ 15 min)"),
                     ("hypo_extended", "Förlängd hypo (< 3,9 i > 120 min)"), ("hyper_level1", "Hyper nivå 1 (> 10,0 i ≥ 15 min)"),
                     ("hyper_level2", "Hyper nivå 2 (> 13,9 i ≥ 15 min)")):
        lines.append(f"| {label} | {cur[f'n_{t}']} | {cur[f'n_{t}_clean']} | {prev.get(f'n_{t}', '–')} |")
    lines += [
        "", "## Läsanvisning", "",
        (f"- Tid under 3,9 utan misstänkta artefakter (kompressionslågor, orimliga hopp): "
         f"{_num(cur.get('tbr_pct_clean'))} %. Skillnaden mot {_num(cur.get('tbr_pct'))} % är andelen som kan "
         "vara sensorfel."),
        ("- Jämförelsen med föregående period är beskrivande. Den säger inte varför något ändrats; "
         "en sådan fråga är en studie."),
        "- Konsensusmålen gäller de flesta vuxna med typ 1-diabetes. Individuella mål sätts med vården.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dagar", type=int, default=30)
    parser.add_argument("--till", type=date.fromisoformat, help="sista dagen (förval: senaste dagen med data)")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "selvra.duckdb")
    args = parser.parse_args(argv)
    with duckdb.connect(str(args.db), read_only=True) as con:
        end = args.till or con.execute("select max(reading_date) from intermediate.int_cgm_flagged").fetchone()[0]
        if end is None:
            print("Ingen data i databasen.", file=sys.stderr)
            return 2
        start = end - timedelta(days=args.dagar - 1)
        prev_end = start - timedelta(days=1)
        cur = period_metrics(con, start, end)
        prev = period_metrics(con, prev_end - timedelta(days=args.dagar - 1), prev_end)
        text = render(cur, prev if prev["n"] else {}, start, end, data_version(con))
    out = ROOT / "data" / "rapporter" / f"glukos-{start}-{end}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    print(f"Sparad: {out.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
