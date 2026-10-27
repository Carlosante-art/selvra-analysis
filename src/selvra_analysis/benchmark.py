"""Benchmark for the design review: frozen cases with a known answer.

Each case is a study file, a synthetic person (scenario) and an answer key (facit). The same
cases go through the design review (`granska`) and through a language model with and without
the knowledge base, and every answer is scored mechanically against the key. Format and the
meaning of every field: benchmark/README.md.

    uv run python -m selvra_analysis.benchmark granska                 # the design review
    uv run python -m selvra_analysis.benchmark llm                     # a language model alone
    uv run python -m selvra_analysis.benchmark llm --kunskap           # the same, with docs/studiedesign.md
    uv run python -m selvra_analysis.benchmark frys                    # rewrite the manifest (new cases only)

The runner refuses cases that differ from the manifest benchmark/FRYST.sha256: a case is
changed by adding a new one, never by editing it after results have been seen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import anthropic
import duckdb
import numpy as np
import pandas as pd
import yaml

from selvra_analysis import granska
from selvra_analysis import study as st
from selvra_analysis.provenance import ROOT

BENCH = ROOT / "benchmark"
SETS = ("fall", "dold", "dold2")
MANIFEST = BENCH / "FRYST.sha256"
RESULTS = BENCH / "resultat"
DEFAULT_MODEL = os.environ.get("SELVRA_BENCHMARK_MODEL", "claude-opus-5-5")
CHECK_IDS = {
    "struktur": "studiefilen saknar något som behövs för att granska eller genomföra studien",
    "tid": "tidsplanen håller inte (startdatum, studiens längd)",
    "tidsordning": "den negativa kontrollen eller utfallet ligger fel i tid i förhållande till exponeringen",
    "overforing": "en dags villkor kan påverka en annan analyserad dag",
    "positivitet": "ett villkor går inte att genomföra eller verifiera på de tillåtna dagarna",
    "apparat": "mätningen av villkoret kommer från olika apparater",
    "underlag": "för lite giltig data för att testet ska kunna ge ett svar",
    "styrka": "för låg styrka för att upptäcka den minsta relevanta effekten",
    "dagtyp": "exponerade dagar och jämförelsedagar skiljer sig i dagstyp (arbete/ledig, vardag/helg)",
    "data": "fel datakälla",
}


# --- Scenario: a synthetic person ------------------------------------------------------------

def _workday(scn: dict, d: date, start: date) -> bool:
    a = scn.get("arbete") or {"monster": "inget"}
    if a["monster"] == "vardagar":
        return d.weekday() < 5
    if a["monster"] == "rullande":
        cycle = a["cykel"]
        return bool(cycle[(d - start).days % len(cycle)])
    return False


def _device(scn: dict, d: date) -> str | None:
    dev = scn.get("apparat") or {"alla": "oura"}
    if "alla" in dev:
        return dev["alla"]
    return dev["fore"] if d < dev["byte"] else dev["efter"]


def _day_rows(scn: dict, rng: np.random.Generator) -> list[dict]:
    start, n = scn["start"], scn["dagar"]
    steps, gl, tr = scn.get("steg"), scn.get("glukos") or {}, scn.get("traning") or {}
    logged = (scn.get("arbete") or {}).get("loggat", False)
    rows, trained_yesterday = [], False
    for i in range(n):
        d = start + timedelta(days=i)
        work = _workday(scn, d, start)
        s = None
        if steps:
            base = steps["arbete"] if work else steps["ledig"]
            s = max(0, int(base + rng.normal(0, steps.get("sd", 800))))
        p = tr.get("p_arbete", tr.get("p", 0.0)) if work else tr.get("p", 0.0)
        trained = bool(rng.random() < p)
        rows.append({
            "reading_date": d, "work": work, "is_workday": work and logged, "steps": s,
            "wearable_source": _device(scn, d) if steps else None,
            "high_steps": None if s is None else s >= 10000, "had_training": trained,
            "day_level": gl.get("dag", 8.0) + rng.normal(0, gl.get("sd", 1.0)) + (gl.get("arbete", 0.0) if work else 0.0),
            "night_level": gl.get("natt", 7.0) + rng.normal(0, gl.get("sd", 1.0))
            - (tr.get("natt_effekt", 0.0) if trained_yesterday else 0.0),
            "valid": bool(rng.random() < scn.get("tackning", 1.0)),
        })
        trained_yesterday = trained
    return rows


def build_db(scn: dict, path: Path) -> None:
    """A database with exactly the tables the design review reads, for one synthetic person."""
    rng = np.random.default_rng(scn.get("seed", 0))
    rows = _day_rows(scn, rng)
    minutes = np.arange(0, 24 * 60, 5)
    frames = []
    for r in rows:
        keep = minutes if r["valid"] else minutes[::3]  # an invalid day: a third of the readings
        level = np.where(keep < 7 * 60, r["night_level"], r["day_level"])
        frames.append(pd.DataFrame({
            "reading_at_local": [datetime.combine(r["reading_date"], datetime.min.time()) + timedelta(minutes=int(m))
                                 for m in keep],
            "reading_date": r["reading_date"], "glucose_mmol": level,
            "flag_compression_low": False, "flag_implausible_jump": False}))
    readings = pd.concat(frames, ignore_index=True)
    days = pd.DataFrame([{k: r[k] for k in ("reading_date", "is_workday", "steps", "wearable_source",
                                             "high_steps", "had_training")} | {"is_valid_day": r["valid"]}
                         for r in rows])
    path.unlink(missing_ok=True)
    with duckdb.connect(str(path)) as con:
        con.execute("create schema intermediate; create schema raw; create schema marts")
        con.register("r", readings)
        con.execute("create table intermediate.int_cgm_flagged as select * from r")
        con.register("d", days)
        con.execute("create table marts.mart_analysis_days as select * from d")
        con.execute("create table raw.source_files (kind varchar, sha256 varchar, bytes bigint, "
                    "n_rows bigint, loaded_at varchar)")
        con.execute("insert into raw.source_files values ('benchmark', 'x', 1, 1, 'now')")
        con.execute("create table raw.clarity_events as select 'EGV' as event_type, 'BENCH' as source_device_id")


# --- Cases and the manifest ------------------------------------------------------------------

def cases(which: str = "alla") -> list[Path]:
    sets = SETS if which == "alla" else (which,)
    return sorted(p for s in sets for p in (BENCH / s).glob("*") if (p / "facit.yml").exists())


def _case_files() -> list[Path]:
    return sorted(f for s in SETS for f in (BENCH / s).rglob("*") if f.is_file())


def write_manifest() -> int:
    files = _case_files()
    MANIFEST.write_text("".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(BENCH)}\n"
                                for f in files))
    return len(files)


def check_manifest() -> None:
    if not MANIFEST.exists():
        raise SystemExit("benchmark/FRYST.sha256 saknas: frys fallen först")
    frozen = dict(reversed(line.split("  ", 1)) for line in MANIFEST.read_text().splitlines() if line)
    now = {str(f.relative_to(BENCH)): hashlib.sha256(f.read_bytes()).hexdigest() for f in _case_files()}
    changed = sorted(k for k in set(frozen) | set(now) if frozen.get(k) != now.get(k))
    if changed:
        raise SystemExit("fallen skiljer sig från FRYST.sha256 (ändra inte fall, lägg till nya): "
                         + ", ".join(changed[:10]))


def _load(case: Path) -> tuple[dict, dict]:
    return (yaml.safe_load((case / "scenario.yml").read_text()), yaml.safe_load((case / "facit.yml").read_text()))


# --- Arms ------------------------------------------------------------------------------------

def run_granska(case: Path, workdir: Path) -> dict:
    scn, _ = _load(case)
    db = workdir / f"{case.name}.duckdb"
    build_db(scn, db)
    try:
        study = st.load(case / "studie.yml")
    except st.StudyError as err:
        return {"dom": "STOPP", "stopp": ["struktur"], "varningar": [], "detalj": str(err)}
    with duckdb.connect(str(db), read_only=True) as con:
        result = granska.review(study, con, today=scn["idag"])
    checks = result["checks"]
    return {"dom": "STOPP" if result["verdict"] == granska.STOPP else "GODKANN",
            "stopp": sorted({c["id"] for c in checks if c["level"] == granska.STOPP}),
            "varningar": sorted({c["id"] for c in checks if c["level"] == granska.VARNING}),
            "detalj": [f"{c['level']} {c['id']}: {c['text']}" for c in checks if c["level"] != granska.OK]}


def data_table(scn: dict, workdir: Path, name: str) -> str:
    """What an analyst would be handed: one row per day, no derived verdicts."""
    db = workdir / f"{name}-tabell.duckdb"
    build_db(scn, db)
    with duckdb.connect(str(db), read_only=True) as con:
        df = con.execute("""
            select d.reading_date as datum, dayname(d.reading_date) as veckodag, d.steps as steg,
                   d.is_workday as arbetspass_loggat, d.wearable_source as apparat, d.had_training as traning,
                   d.is_valid_day as giltig_dag,
                   round(avg(case when hour(r.reading_at_local) >= 7 then r.glucose_mmol end), 2) as medel_07_24,
                   round(avg(case when hour(r.reading_at_local) < 6 then r.glucose_mmol end), 2) as medel_00_06
            from marts.mart_analysis_days as d
            left join intermediate.int_cgm_flagged as r using (reading_date)
            group by all order by datum""").df()
    return df.to_csv(index=False)


def _prompt(case: Path, scn: dict, table: str, knowledge: bool) -> tuple[str, str]:
    ids = "\n".join(f"- {k}: {v}" for k, v in CHECK_IDS.items())
    system = (
        "Du granskar en studieplan innan den låses. Studien görs på en enda persons egna data: CGM-glukos "
        "var 5:e minut, steg från en wearable och loggade händelser. Avgör om planen ska stoppas (den kan inte "
        "ge ett försvarbart svar som den är skriven) eller godkännas (eventuellt med varningar).\n\n"
        f"Möjliga skäl, ange id:\n{ids}\n\n"
        'Svara endast med JSON: {"dom": "STOPP" eller "GODKANN", "stopp": [id], "varningar": [id], '
        '"motivering": "högst 80 ord"}')
    if knowledge:
        system += "\n\nKUNSKAPSBAS:\n" + (ROOT / "docs" / "studiedesign.md").read_text()
    user = (f"Dagens datum: {scn['idag']}\n\nSTUDIEFIL:\n{(case / 'studie.yml').read_text()}\n\n"
            f"DATA, en rad per dag (de senaste {scn['dagar']} dagarna):\n{table}")
    return system, user


def run_llm(case: Path, workdir: Path, knowledge: bool, model: str) -> dict:
    scn, _ = _load(case)
    system, user = _prompt(case, scn, data_table(scn, workdir, case.name), knowledge)
    msg = anthropic.Anthropic().messages.create(model=model, max_tokens=800, system=system,
                                                messages=[{"role": "user", "content": user}])
    raw = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        ans = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        ans = {}
    dom = "STOPP" if str(ans.get("dom", "")).upper().startswith("STOPP") else "GODKANN"
    return {"dom": dom, "stopp": sorted(set(ans.get("stopp") or [])), "varningar": sorted(set(ans.get("varningar") or [])),
            "detalj": ans.get("motivering", raw[:500]), "ogiltigt_svar": not ans}


# --- Scoring ---------------------------------------------------------------------------------

def score(facit: dict, ans: dict) -> dict:
    """Right verdict, and for the right reason.

    A case that should be stopped counts as stopped for the right reason only if one of the
    key's reasons is among the stops. A case that should pass must not be stopped, and must
    carry every warning the key requires.
    """
    if facit["forvantat"] == "STOPP":
        right = ans["dom"] == "STOPP"
        reason = right and bool(set(ans["stopp"]) & set(facit["skal"]))
    else:
        right = ans["dom"] == "GODKANN"
        reason = right and set(facit.get("flagga") or []) <= set(ans["varningar"]) | set(ans["stopp"])
    return {"ratt_dom": right, "ratt_skal": reason}


def summarise(rows: list[dict]) -> dict:
    stop = [r for r in rows if r["facit"]["forvantat"] == "STOPP"]
    good = [r for r in rows if r["facit"]["forvantat"] == "GODKANN"]
    return {
        "fall": len(rows),
        "stoppfrekvens": f"{sum(r['ratt_dom'] for r in stop)}/{len(stop)}",
        "stopp_av_ratt_skal": f"{sum(r['ratt_skal'] for r in stop)}/{len(stop)}",
        "godkannandefrekvens": f"{sum(r['ratt_dom'] for r in good)}/{len(good)}",
        "godkanda_med_ratt_flaggor": f"{sum(r['ratt_skal'] for r in good)}/{len(good)}",
        "falska_godkannanden": [r["fall"] for r in stop if not r["ratt_dom"]],
        "falska_stopp": [r["fall"] for r in good if not r["ratt_dom"]],
        "ratt_dom_fel_skal": [r["fall"] for r in rows if r["ratt_dom"] and not r["ratt_skal"]],
    }


def run(arm: str, which: str, model: str) -> dict:
    check_manifest()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases(which):
            _, facit = _load(case)
            if arm == "granska":
                ans = run_granska(case, Path(tmp))
            else:
                ans = run_llm(case, Path(tmp), knowledge=arm == "llm+kunskap", model=model)
            rows.append({"fall": f"{case.parent.name}/{case.name}", "facit": facit, "svar": ans, **score(facit, ans)})
    out = {"arm": arm, "modell": None if arm == "granska" else model, "uppsattning": which,
           "kord": datetime.now(UTC).isoformat(timespec="seconds"),
           "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
           "sammanfattning": summarise(rows), "fall": rows}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{out['kord'].replace(':', '')}-{arm}-{which}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str) + "\n")
    return out


def render(out: dict) -> str:
    s = out["sammanfattning"]
    lines = [f"Benchmark {out['arm']}" + (f" ({out['modell']})" if out["modell"] else "") + f", {out['uppsattning']}",
             "", f"  stoppfrekvens          {s['stoppfrekvens']}  (av rätt skäl {s['stopp_av_ratt_skal']})",
             f"  godkännandefrekvens    {s['godkannandefrekvens']}  (med rätt flaggor {s['godkanda_med_ratt_flaggor']})",
             f"  falska godkännanden    {', '.join(s['falska_godkannanden']) or 'inga'}",
             f"  falska stopp           {', '.join(s['falska_stopp']) or 'inga'}",
             f"  rätt dom, fel skäl     {', '.join(s['ratt_dom_fel_skal']) or 'inga'}", ""]
    for r in out["fall"]:
        mark = "OK " if r["ratt_skal"] else ("½  " if r["ratt_dom"] else "FEL")
        lines.append(f"  {mark} {r['fall']:<42} facit {r['facit']['forvantat']:<8} svar {r['svar']['dom']:<8} "
                     f"stopp {r['svar']['stopp']} varn {r['svar']['varningar']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="kommando", required=True)
    sub.add_parser("frys", help="skriv manifestet över fallen")
    g = sub.add_parser("granska", help="kör designgranskningen på fallen")
    g.add_argument("--uppsattning", choices=["alla", *SETS], default="alla")
    m = sub.add_parser("llm", help="kör en språkmodell på samma fall (kräver ANTHROPIC_API_KEY)")
    m.add_argument("--kunskap", action="store_true", help="ge modellen docs/studiedesign.md")
    m.add_argument("--modell", default=DEFAULT_MODEL)
    m.add_argument("--uppsattning", choices=["alla", *SETS], default="alla")
    args = parser.parse_args(argv)
    if args.kommando == "frys":
        print(f"Fryst: {write_manifest()} filer i {MANIFEST.relative_to(ROOT)}")
        return 0
    arm = "granska" if args.kommando == "granska" else ("llm+kunskap" if args.kunskap else "llm")
    out = run(arm, args.uppsattning, getattr(args, "modell", DEFAULT_MODEL))
    print(render(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
