"""The study engine: a study is a file, the engine does the rest.

A study is described in `studies/<id>/studie.yml` (format in studies/README.md).
Its life has four steps, each a command:

    validera  check the file; nothing is written
    las       lock it: checksum of the file, the git commit of the pipeline, and for an
              experiment the randomised schedule (drawn from the OS's random source).
              Commit the folder afterwards: the commit is the public timestamp.
    status    progress and data quality so far. Never the effect: an experiment is
              analysed once, when it is complete, so no one can stop it when it looks good.
    kor       the single confirmatory analysis, when the study is complete: decision by
              the locked rule, a run record and a report.

    python -m selvra_analysis.study status studies/002-promenad/studie.yml --db data/selvra.duckdb

Designs:
    n1           randomised paired periods (A/B), randomisation test on a local-time window
    observation  days after a logged event vs other days, block bootstrap; on data that
                 already exists it is marked retrospective in every report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from selvra_analysis import n1
from selvra_analysis.provenance import PIPELINE_PATHS, ROOT, _git, data_version
from selvra_analysis.stats import block_bootstrap_difference, daily_series

WINDOW_METRICS = {"medel": "mean_mmol", "topp": "peak_mmol", "tid_over_10": "tar_pct"}
EVENT_COLUMNS = {
    "alkohol": "had_alcohol", "traning": "had_training", "sjukdom": "is_ill",
    "stress": "had_stress", "resa": "is_travelling", "menstruation": "is_menstruating",
    "medicinandring": "had_medication_change",
}
REQUIRED_TEXT = ["id", "titel", "fraga", "tes", "motbevis"]


class StudyError(ValueError):
    pass


@dataclass
class Study:
    path: Path
    spec: dict

    @property
    def folder(self) -> Path:
        return self.path.parent

    @property
    def design(self) -> dict:
        return self.spec["design"]

    @property
    def kind(self) -> str:
        return self.design["typ"]

    @property
    def lock_path(self) -> Path:
        return self.folder / "las.json"

    @property
    def schedule_path(self) -> Path:
        return self.folder / "schema.csv"


# --- Validation -------------------------------------------------------------------------------

def _need(cond: bool, errors: list[str], msg: str) -> None:
    if not cond:
        errors.append(msg)


def load(path: Path) -> Study:
    spec = yaml.safe_load(path.read_text())
    errors = validate(spec)
    if errors:
        raise StudyError(f"{path}:\n  " + "\n  ".join(errors))
    return Study(path, spec)


def validate(spec: dict) -> list[str]:
    """All problems with a study file, in Swedish, or an empty list."""
    e: list[str] = []
    if not isinstance(spec, dict):
        return ["filen är inte en YAML-karta"]
    for key in REQUIRED_TEXT:
        _need(isinstance(spec.get(key), str) and spec[key].strip() != "", e, f"saknar text: {key}")
    design, outcome, analysis = spec.get("design") or {}, spec.get("utfall") or {}, spec.get("analys") or {}
    kind = design.get("typ")
    _need(kind in {"n1", "observation"}, e, "design.typ måste vara n1 eller observation")

    s = analysis.get("minsta_relevanta_effekt")
    _need(isinstance(s, (int, float)) and s != 0, e,
          "analys.minsta_relevanta_effekt: ett tal skilt från 0; tecknet anger förväntad riktning (A minus B)")
    level = analysis.get("niva", 0.95)
    _need(isinstance(level, float) and 0.5 < level < 1, e, "analys.niva: mellan 0,5 och 1, t.ex. 0.95")

    if kind == "n1":
        for key in ("A", "B"):
            _need(isinstance(design.get(key), str), e, f"design.{key}: beskriv villkoret exakt")
        _need(isinstance(design.get("start"), date), e, "design.start: datum ÅÅÅÅ-MM-DD")
        pairs, days, wash = design.get("par"), design.get("periodlangd_dagar"), design.get("tvatt_dagar", 0)
        _need(isinstance(pairs, int) and pairs >= 6, e,
              "design.par: minst 6 (med färre kan testet aldrig nå 5 %)")
        _need(isinstance(days, int) and days >= 1, e, "design.periodlangd_dagar: heltal ≥ 1")
        _need(isinstance(wash, int) and isinstance(days, int) and 0 <= wash < days, e,
              "design.tvatt_dagar: mellan 0 och periodlängden − 1")
        _need(analysis.get("metod") == "randomiseringstest", e, "analys.metod: randomiseringstest för n1")
        _need(outcome.get("matt") in WINDOW_METRICS, e, f"utfall.matt: en av {sorted(WINDOW_METRICS)}")
        window = outcome.get("fonster")
        _need(isinstance(window, list) and len(window) == 2 and all(isinstance(t, str) for t in window), e,
              'utfall.fonster: ["HH:MM", "HH:MM"] i lokal tid')
    elif kind == "observation":
        exp = design.get("exponering") or {}
        _need(exp.get("handelse") in EVENT_COLUMNS, e, f"design.exponering.handelse: en av {sorted(EVENT_COLUMNS)}")
        _need(isinstance(exp.get("dagar_efter", 0), int) and exp.get("dagar_efter", 0) >= 0, e,
              "design.exponering.dagar_efter: heltal ≥ 0")
        period = design.get("period")
        _need(isinstance(period, list) and len(period) == 2 and all(isinstance(d, date) for d in period),
              e, "design.period: [från, till] som datum")
        _need(isinstance(design.get("retrospektiv"), bool), e,
              "design.retrospektiv: true om datan redan fanns när studien skrevs")
        _need(analysis.get("metod") == "blockbootstrap", e, "analys.metod: blockbootstrap för observation")
        _need(isinstance(analysis.get("blocklangd"), int) and analysis["blocklangd"] >= 1, e,
              "analys.blocklangd: dagar, heltal ≥ 1")
        _need(isinstance(outcome.get("kolumn"), str), e,
              "utfall.kolumn: en kolumn i marts.mart_analysis_days, t.ex. tbr_pct")
    return e


# --- Lock -------------------------------------------------------------------------------------

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock(study: Study, seed: int | None = None) -> dict:
    if study.lock_path.exists():
        raise StudyError("studien är redan låst; en ändring kräver en ny studie med nytt id")
    record = {
        "study": study.spec["id"],
        "locked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "spec_sha256": _sha(study.path),
        "pipeline_commit": _git("rev-parse", "HEAD"),
    }
    if study.kind == "n1":
        d = study.design
        seed = seed if seed is not None else secrets.randbits(32)
        sched = n1.make_schedule(d["start"], d["par"], d["periodlangd_dagar"], d.get("tvatt_dagar", 0), seed)
        record["schedule_sha256"] = n1.write_schedule(sched, study.schedule_path, seed)
        record["schedule_end"] = str(sched["date"].max())
    study.lock_path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def check_lock(study: Study) -> dict:
    """The lock must exist, match the files, and the pipeline must not have changed since."""
    if not study.lock_path.exists():
        raise StudyError("studien är inte låst: kör `las` och committa mappen")
    rec = json.loads(study.lock_path.read_text())
    problems = []
    if _sha(study.path) != rec["spec_sha256"]:
        problems.append("studie.yml har ändrats efter låsningen")
    if study.kind == "n1" and _sha(study.schedule_path) != rec["schedule_sha256"]:
        problems.append("schema.csv har ändrats efter låsningen")
    rel = [str(p) for p in (study.path, study.lock_path, study.schedule_path) if p.exists()]
    if _git("status", "--porcelain", "--", *rel):
        problems.append("studiemappen är inte committad: commit är den offentliga tidsstämpeln")
    changed = _git("diff", "--name-only", rec["pipeline_commit"], "HEAD", "--", *PIPELINE_PATHS)
    dirty = _git("status", "--porcelain", "--", *PIPELINE_PATHS)
    if changed or dirty:
        problems.append("pipelinen har ändrats sedan låsningen:\n    " + "\n    ".join(
            (changed + "\n" + dirty).split()))
    if problems:
        raise StudyError("låsningen håller inte:\n  " + "\n  ".join(problems))
    return rec


# --- Data -------------------------------------------------------------------------------------

def _daily_outcome(study: Study, con) -> tuple[pd.DataFrame, str]:
    o = study.spec["utfall"]
    if study.kind == "n1":
        daily = n1.window_outcomes(con, o["fonster"][0], o["fonster"][1], o.get("min_tackning_pct", 70.0))
        return daily, WINDOW_METRICS[o["matt"]]
    daily = con.execute("select * from marts.mart_analysis_days").df()
    if o["kolumn"] not in daily.columns:
        raise StudyError(f"utfall.kolumn {o['kolumn']!r} finns inte i mart_analysis_days")
    return daily, o["kolumn"]


def _observation_series(study: Study, daily: pd.DataFrame, col: str) -> pd.DataFrame:
    d = study.design
    exp = d["exponering"]
    s = daily_series(daily, "reading_date", [col, EVENT_COLUMNS[exp["handelse"]], "is_valid_day"])
    lo, hi = (pd.Timestamp(x) for x in d["period"])
    flag = s[EVENT_COLUMNS[exp["handelse"]]].shift(exp.get("dagar_efter", 0))
    s["exposed"] = flag.map({True: True, False: False})
    s["y"] = s[col].where(s["is_valid_day"] == True)
    return s[(s.index >= lo) & (s.index <= hi)]


# --- Status (blind) ---------------------------------------------------------------------------

def status(study: Study, con, today: date | None = None) -> str:
    rec = check_lock(study)
    today = today or date.today()
    daily, col = _daily_outcome(study, con)
    lines = [f"# Status · {study.spec['titel']}", "", (f"*{today} · studie `{study.spec['id']}` · "
              f"låst {rec['locked_at'][:10]}*"), "",
             ("Statusrapporten visar framsteg och datakvalitet, aldrig effekten. Effekten räknas en gång, "
              "när studien är klar."), ""]
    if study.kind == "n1":
        sched = n1.read_schedule(study.schedule_path)
        periods = n1.period_outcomes(sched, daily, col)
        end = sched.groupby("period")["date"].max()
        periods["klar"] = periods["period"].map(end) < today
        done = periods[periods["klar"]]
        complete_pairs = done.groupby("pair")["value"].apply(lambda v: v.notna().sum() == 2)
        n_pairs = sched["pair"].max()
        lines += [
            f"- **Period:** {sched['date'].min()} till {sched['date'].max()}",
            f"- **Avslutade perioder:** {len(done)} av {2 * n_pairs}",
            f"- **Kompletta par hittills:** {int(complete_pairs.sum())} av {n_pairs}",
            f"- **Avslutade perioder utan giltig data:** {int(done['value'].isna().sum())}",
        ]
        upcoming = sched[sched["date"] >= today].head(3)
        if not upcoming.empty:
            lines += ["", "**Kommande dagar enligt schemat:**", ""]
            for r in upcoming.itertuples():
                cond = study.design[r.condition]
                lines.append(f"- {r.date}: {r.condition} ({cond}){' · tvättdag' if r.washout else ''}")
        lines += ["", f"Slutanalysen kan köras från {date.fromisoformat(rec['schedule_end']) + timedelta(days=1)}."]
    else:
        s = _observation_series(study, daily, col)
        lines += [
            f"- **Period:** {study.design['period'][0]} till {study.design['period'][1]}",
            f"- **Exponerade dagar med giltigt utfall:** {int((s['exposed'].eq(True) & s['y'].notna()).sum())}",
            f"- **Jämförelsedagar med giltigt utfall:** {int((s['exposed'].eq(False) & s['y'].notna()).sum())}",
        ]
        if study.design["retrospektiv"]:
            lines += ["", "*Retrospektiv: datan fanns när studien skrevs.*"]
    return "\n".join(lines) + "\n"


# --- Final run --------------------------------------------------------------------------------

def decide(estimate: dict, smallest: float) -> str:
    """The locked decision rule. `smallest` carries the expected direction (A minus B)."""
    lo, hi = estimate["ci_low"], estimate["ci_high"]
    if smallest < 0:
        lo, hi, smallest = -hi, -lo, -smallest
    if lo > smallest:
        return "tesen håller: hela intervallet visar minst den minsta relevanta effekten, i förväntad riktning"
    if hi < smallest:
        return "tesen motbevisad: hela intervallet visar en mindre effekt än den minsta relevanta, eller en effekt åt andra hållet"
    return "obestämt: intervallet rymmer både en relevant och en irrelevant effekt"


def run(study: Study, con, today: date | None = None) -> tuple[dict, str]:
    rec = check_lock(study)
    today = today or date.today()
    runs = study.folder / "korningar"
    if any(runs.glob("*.json")):
        raise StudyError("slutanalysen är redan körd; den körs en gång")
    a = study.spec["analys"]
    daily, col = _daily_outcome(study, con)

    if study.kind == "n1":
        if today <= date.fromisoformat(rec["schedule_end"]):
            raise StudyError(f"studien pågår till {rec['schedule_end']}; slutanalysen körs efter det")
        sched = n1.read_schedule(study.schedule_path)
        periods = n1.period_outcomes(sched, daily, col)
        est = n1.randomisation_test(periods, level=a.get("niva", 0.95)).as_dict()
        extra = {"perioder": periods.to_dict("records")}
    else:
        s = _observation_series(study, daily, col)
        est = block_bootstrap_difference(s["y"], s["exposed"], block_length=a["blocklangd"],
                                         seed=a.get("seed", 1), level=a.get("niva", 0.95)).as_dict()
        extra = {}

    verdict = decide(est, a["minsta_relevanta_effekt"])
    record = {
        "study": study.spec["id"], "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lock": rec, "commit": _git("rev-parse", "HEAD"), "data": data_version(con),
        "result": est, "beslut": verdict, **extra,
    }
    runs.mkdir(exist_ok=True)
    (runs / f"{record['run_at'].replace(':', '')}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False, default=str) + "\n")
    report = _report(study, record)
    (study.folder / "slutrapport.md").write_text(report)
    return record, report


def _fmt(x: float) -> str:
    return "obegränsat" if not math.isfinite(x) else f"{x:+.2f}".replace(".", ",")


def _report(study: Study, record: dict) -> str:
    sp, r, d = study.spec, record["result"], study.design
    unit = "procentenheter" if sp["utfall"].get("matt") == "tid_over_10" or \
        str(sp["utfall"].get("kolumn", "")).endswith("_pct") else "mmol/L"
    kind = ("randomiserat n-of-1-försök med parade perioder" if study.kind == "n1"
            else "observationsstudie" + (", retrospektiv" if d.get("retrospektiv") else ""))
    lines = [
        f"# {sp['titel']}", "",
        f"*{kind} · studie `{sp['id']}` · låst {record['lock']['locked_at'][:10]} · körd {record['run_at'][:10]}*", "",
        "## Svar", "",
        (f"**{record['beslut'][0].upper() + record['beslut'][1:]}.** Skattning {_fmt(r['estimate'])} {unit} "
         f"({int(r['level'] * 100)} % intervall {_fmt(r['ci_low'])} till {_fmt(r['ci_high'])})."), "",
        "## Fråga och tes (låsta i förväg)", "",
        f"- **Fråga:** {sp['fraga']}", f"- **Tes:** {sp['tes']}", f"- **Motbevis:** {sp['motbevis']}",
        f"- **Minsta relevanta effekt:** {_fmt(sp['analys']['minsta_relevanta_effekt'])} {unit}", "",
        "## Metod", "",
    ]
    if study.kind == "n1":
        lines += [
            f"- **A:** {d['A']}", f"- **B:** {d['B']}",
            (f"- **Design:** {d['par']} par om två perioder à {d['periodlangd_dagar']} dagar, ordningen inom "
             f"varje par lottad före start; {d.get('tvatt_dagar', 0)} tvättdag(ar) per period räknas inte."),
            (f"- **Utfall:** {sp['utfall']['matt']} glukos {sp['utfall']['fonster'][0]}–{sp['utfall']['fonster'][1]} "
             "lokal tid, medel per period."),
            (f"- **Analys:** parvis randomiseringstest ({'exakt' if r['exact'] else 'Monte Carlo'}), intervall "
             "genom testinvertering. Lottat villkor gäller oavsett följsamhet."), "",
            "## Resultat", "",
            "| | |", "|---|---|",
            f"| Kompletta par | {r['n_pairs']} (bortfall {r['n_pairs_dropped']}) |",
            f"| Skattning A − B | {_fmt(r['estimate'])} {unit} |",
            f"| Intervall | {_fmt(r['ci_low'])} till {_fmt(r['ci_high'])} |",
            f"| p (ingen effekt) | {r['p_value']:.4f} |".replace(".", ","),
            f"| AB-par / BA-par | {_fmt(r['estimate_ab_pairs'])} / {_fmt(r['estimate_ba_pairs'])} |", "",
            "Skiljer sig AB- och BA-paren mycket åt kan en eftereffekt mellan perioderna finnas.",
        ]
    else:
        exp = d["exponering"]
        lines += [
            (f"- **Exponering:** dagar {exp.get('dagar_efter', 0)} dag(ar) efter loggad händelse "
             f"`{exp['handelse']}`, jämfört med övriga dagar, {d['period'][0]} till {d['period'][1]}."),
            f"- **Utfall:** `{sp['utfall']['kolumn']}` på giltiga dagar.",
            f"- **Analys:** skillnad i medelvärde, cirkulär block-bootstrap, block {r['block_length']} dagar.", "",
            "## Resultat", "",
            f"Exponerade dagar {r['n_exposed']}, jämförelsedagar {r['n_comparison']}.", "",
            "Observationsdata visar samband, inte orsak.",
        ]
        if d.get("retrospektiv"):
            lines.append("Studien är retrospektiv: datan fanns när den skrevs, så förregistreringen skyddar "
                         "inte mot att frågan valdes efter att mönstret setts.")
    data = record["data"]
    lines += [
        "", "## Spårbarhet", "",
        f"- Studiefil sha256 `{record['lock']['spec_sha256'][:16]}`, pipeline-commit `{record['lock']['pipeline_commit'][:12]}`",
        f"- Dataversion `{data['fingerprint'][:16]}` ({len(data['files'])} källor)",
        f"- Körd vid commit `{record['commit'][:12]}`",
    ]
    return "\n".join(lines) + "\n"


# --- CLI --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kommando", choices=["validera", "las", "status", "kor"])
    parser.add_argument("studie", type=Path)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "selvra.duckdb")
    args = parser.parse_args(argv)
    try:
        study = load(args.studie.resolve())
        if args.kommando == "validera":
            print(f"OK: {study.spec['id']} ({study.kind})")
        elif args.kommando == "las":
            rec = lock(study)
            print(f"Låst {rec['study']}. Committa nu {study.folder.relative_to(ROOT)}/ — "
                  "commiten är den offentliga tidsstämpeln.")
        else:
            with duckdb.connect(str(args.db), read_only=True) as con:
                if args.kommando == "status":
                    text = status(study, con)
                    out = study.folder / "rapporter" / f"status-{date.today()}.md"
                    out.parent.mkdir(exist_ok=True)
                    out.write_text(text)
                    print(text)
                else:
                    _, report = run(study, con)
                    print(report)
    except StudyError as err:
        print(f"Stopp: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
