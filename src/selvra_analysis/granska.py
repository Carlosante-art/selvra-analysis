"""Design review before a study is locked: every check that can be computed, run on your own data.

The study-design agent (.claude/agents/studiedesigner.md) asks the questions that need a human;
this module answers the ones that need data, the same way every time. `las` refuses unless this
review has passed for exactly the version of the file being locked.

    uv run python -m selvra_analysis.granska studies/NNN-namn/studie.yml --db data/selvra.duckdb

Each check is OK, VARNING (lock allowed; say why in the study file) or STOPP (lock refused).
Sources for every threshold are in docs/studiedesign.md.

n1 checks
    struktur       the file states how adherence is measured and what kind of action A is
    tid            start in the future; calendar span short enough to avoid seasonal drift
    tidsordning    the negative control ends before A can act; the outcome window does not
    overforing     analysed days far enough apart for the action's carryover (Riddell 2017)
    positivitet    both conditions occurred, per day type, in your last 8 weeks (Daza 2018)
    underlag       expected valid pairs after data loss; smallest attainable p below alpha
    styrka         power from your own day-to-day variability on the eligible days
    data           the review ran on real data, not the synthetic demo

observation checks
    underlag       exposed and comparison days with a valid outcome, against minsta_underlag
    dagtyp         exposed and comparison days have a similar share of weekend days
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis import n1
from selvra_analysis import study as st
from selvra_analysis.provenance import ROOT, data_version

OK, VARNING, STOPP = "OK", "VARNING", "STOPP"
HISTORY_DAYS = 56       # positivity: the last 8 weeks
SD_HISTORY_DAYS = 90    # variability and coverage: the last 90 days
MIN_STRATUM_DAYS = 7
MIN_SD_DAYS = 14
MIN_POWER = 0.80
MAX_PAIRS_SEARCHED = 60
MAX_SPAN_DAYS = 120
POWER_SIMS = 500
# Calendar days between two consecutive analysed days: (stop below, warn below, reason).
CARRYOVER = {
    "traning": (2, 3, ("insulinkänsligheten är förhöjd upp till 24–48 h efter träning och "
                       "hypoglykemirisken minst 24 h, nattlig risk störst efter eftermiddagsträning (Riddell 2017)")),
    "alkohol": (2, 2, "alkohol ger fördröjd hypoglykemi morgonen efter, 07–11 (White 2017)"),
    "somn": (1, 2, "en kort natt sänker insulinkänsligheten dagen efter (Donga 2010)"),
    "maltid": (1, 1, ""),
    "annat": (1, 1, ""),
}
WEEKEND = {5, 6}
DAYTYPE_WARN = 0.25   # observation: difference in weekend share between exposed and comparison days
DAYTYPE_STOP = 0.50


@dataclass
class Check:
    id: str
    level: str
    text: str


def _verdict(checks: list[Check]) -> str:
    levels = {c.level for c in checks}
    return STOPP if STOPP in levels else VARNING if VARNING in levels else OK


# --- Data helpers ------------------------------------------------------------------------------

def _columns(con) -> set[str]:
    return {r[0] for r in con.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'marts' and table_name = 'mart_analysis_days'").fetchall()}


def _recent(df: pd.DataFrame, days: int, column: str = "reading_date") -> pd.DataFrame:
    """The last `days` calendar days of the data, as a frame with a date column."""
    df = df.copy()
    df[column] = pd.to_datetime(df[column]).dt.date
    if df.empty:
        return df
    end = df[column].max()
    return df[df[column] > end - timedelta(days=days)]


def _strata(design: dict) -> tuple[list[tuple[str, set[int]]], str | None]:
    """Day types to check, as (name, weekdays), and a caveat when the history is a proxy."""
    days = design.get("dagar") or {}
    if days.get("veckodagar"):
        return [("de tillåtna veckodagarna", {n1.WEEKDAYS[w] for w in days["veckodagar"]})], None
    if days.get("datum"):
        wd = {d.weekday() for d in days["datum"]}
        return [("samma veckodagar som de valda datumen", wd)], (
            "dagarna är en datumlista; historiken approximeras med samma veckodagar, som kan blanda "
            "lediga dagar och arbetsdagar")
    return [("vardagar", {0, 1, 2, 3, 4}), ("helger", WEEKEND)], None


def _analysed_dates(design: dict) -> list[date]:
    """Every analysed day of the study, in calendar order, before randomisation."""
    if "dagar" in design:
        return n1.eligible_dates(design["start"], 2 * design["par"], design["dagar"].get("veckodagar"),
                                 design["dagar"].get("datum"))
    sched = n1.make_schedule(design["start"], design["par"], design["periodlangd_dagar"],
                             design.get("tvatt_dagar", 0), seed=0)
    return list(sched.loc[~sched["washout"], "date"])


def _min_gap_between_periods(design: dict) -> int:
    """Fewest calendar days between the last analysed day of one period and the first of the next,
    which is where one condition's effect can leak into the other's outcome."""
    if "dagar" in design:
        days = _analysed_dates(design)
        return min((b - a).days for a, b in itertools.pairwise(days))
    return design.get("tvatt_dagar", 0) + 1


def _minutes(clock: str) -> int:
    h, m = clock.split(":")
    return int(h) * 60 + int(m)


# --- n1 checks ---------------------------------------------------------------------------------

def _check_structure(design: dict) -> list[Check]:
    out = []
    if "foljsamhet" not in design:
        out.append(Check("struktur", STOPP, "design.foljsamhet saknas: hur verifieras varje dags villkor ur data? "
                                            "(t.ex. {kolumn: steps, A: {min: 10000}, B: {max: 5000}}, eller "
                                            "{kolumn: manuell})"))
    elif design["foljsamhet"].get("kolumn") == "manuell":
        out.append(Check("struktur", VARNING, "följsamheten är självrapporterad (kolumn: manuell); den kan inte "
                                              "kontrolleras mot data och positiviteten kan inte prövas"))
    if "verkan" not in design:
        out.append(Check("struktur", STOPP, "design.verkan saknas: {typ: traning|alkohol|somn|maltid|annat, "
                                            "borjar: \"HH:MM\"} styr kontrollen av överföring och tidsordning"))
    return out


def _check_time(design: dict, today: date) -> list[Check]:
    days = _analysed_dates(design)
    span = (days[-1] - design["start"]).days + 1
    out = []
    if design["start"] <= today:
        out.append(Check("tid", STOPP, f"start {design['start']} är inte i framtiden; schemat måste lottas före "
                                       "första försöksdagen"))
    level = VARNING if span > MAX_SPAN_DAYS else OK
    out.append(Check("tid", level, f"{len(days)} analyserade dagar från {design['start']} till {days[-1]} "
                                   f"({span} kalenderdagar)" + (
                                       "; över fyra månader ger säsong, sensorbyten och formförändring tid att "
                                       "glida, paren balanserar bara långsam drift" if level == VARNING else "")))
    return out


def _check_order(spec: dict) -> list[Check]:
    start = _minutes(spec["design"]["verkan"]["borjar"])
    out = []
    neg = spec["negativ_kontroll"]
    if "fonster" in neg:
        end = _minutes(neg["fonster"][1])
        if end > start:
            out.append(Check("tidsordning", STOPP,
                             f"negativa kontrollen slutar {neg['fonster'][1]}, efter att A kan börja verka "
                             f"{spec['design']['verkan']['borjar']}; den kan då påverkas av A"))
        else:
            out.append(Check("tidsordning", OK, "negativa kontrollen ligger före A samma dag"))
    o = spec["utfall"]
    if "fonster" in o and _minutes(o["fonster"][1]) <= start:
        out.append(Check("tidsordning", STOPP, f"utfallsfönstret slutar {o['fonster'][1]}, innan A kan verka"))
    return out


def _check_carryover(spec: dict) -> list[Check]:
    d = spec["design"]
    kind = d["verkan"]["typ"]
    stop, warn, why = CARRYOVER[kind]
    gap = _min_gap_between_periods(d)
    night_control = "fonster" in spec["negativ_kontroll"] and _minutes(spec["negativ_kontroll"]["fonster"][0]) < 360
    tail = (" Den nattliga negativa kontrollen ligger då också i förra A-dagens eftereffekt och prövar inget."
            if night_control and gap < warn else "")
    text = f"minst {gap} kalenderdag(ar) mellan två analyserade dagar med olika villkor; {why or 'kort verkan'}."
    if gap < stop:
        return [Check("overforing", STOPP, text + f" Kräver minst {stop}, helst {warn}: lägg tvättdagar eller "
                                                  "välj tillåtna dagar som inte ligger intill varandra." + tail)]
    if gap < warn:
        return [Check("overforing", VARNING, text + f" Helst {warn}; redovisa AB mot BA." + tail)]
    return [Check("overforing", OK, text)]


def _check_positivity(spec: dict, con) -> list[Check]:
    d = spec["design"]
    f = d.get("foljsamhet") or {}
    col = f.get("kolumn")
    if not col or col == "manuell":
        return []
    if col not in _columns(con):
        return [Check("positivitet", STOPP, f"kolumnen {col!r} finns inte i marts.mart_analysis_days")]
    hist = _recent(con.execute(f'select reading_date, "{col}" as x from marts.mart_analysis_days').df(),  # noqa: S608
                   HISTORY_DAYS)
    hist = hist[hist["x"].notna()]
    if hist.empty:
        return [Check("positivitet", STOPP,
                      f"ingen mätning av {col} de senaste {HISTORY_DAYS} dagarna: varken positivitet eller "
                      "följsamhet går att verifiera. Ladda källan (Oura: OURA_TOKEN och make live) eller "
                      "ange kolumn: manuell och motivera")]
    out_source = _check_one_device(con, hist)
    strata, caveat = _strata(d)
    weekday = pd.to_datetime(hist["reading_date"]).dt.day_of_week
    rows, out = [], []
    justified = isinstance(d.get("genomforbarhet"), str) and d["genomforbarhet"].strip() != ""
    for name, wd in strata:
        x = hist.loc[weekday.isin(wd), "x"]
        n = len(x)
        n_a = int(x.map(lambda v: st.meets(float(v), f["A"])).sum())
        n_b = int(x.map(lambda v: st.meets(float(v), f["B"])).sum())
        rows.append(f"{name}: {n} dagar, A uppfyllt {n_a}, B uppfyllt {n_b}, median {x.median():.0f}"
                    if n else f"{name}: inga dagar med mätning")
        if n < MIN_STRATUM_DAYS:
            out.append(Check("positivitet", VARNING, f"{name}: bara {n} dagar med mätning; för lite för att bedöma"))
            continue
        for cond, k in (("A", n_a), ("B", n_b)):
            if k == 0:
                out.append(Check("positivitet", VARNING if justified else STOPP,
                                 f"{cond} inträffade inte en enda gång på {name} under {HISTORY_DAYS} dagar. "
                                 + ("Motiverat i design.genomforbarhet." if justified else
                                    "Antingen är villkoret omöjligt där (begränsa design.dagar eller definiera "
                                    "om villkoret relativt dagstypen) eller så ska design.genomforbarhet "
                                    "förklara hur det ska gå till.")))
        for cond, k in (("A", n_a), ("B", n_b)):
            if k >= 0.8 * n:
                other = "B" if cond == "A" else "A"
                out.append(Check("positivitet", VARNING,
                                 f"{name}: {cond} är det vanliga ({k} av {n} dagar), så kontrasten skapas helt av "
                                 f"att du aktivt gör {other}; säkerställ att {other} går att hålla och är säkert"))
    summary = Check("positivitet", OK, "historik per dagstyp: " + "; ".join(rows) +
                    (f" (OBS: {caveat})" if caveat else ""))
    return [summary, *out_source, *out]


def _check_one_device(con, hist: pd.DataFrame) -> list[Check]:
    """Oura and Garmin count steps differently; a series that switches device mid-way is two measures."""
    if "wearable_source" not in _columns(con):
        return []
    src = _recent(con.execute("select reading_date, wearable_source from marts.mart_analysis_days "
                              "where wearable_source is not null").df(), HISTORY_DAYS)
    src = src[src["reading_date"].isin(set(hist["reading_date"]))]
    counts = src["wearable_source"].value_counts().to_dict()
    if len(counts) > 1:
        return [Check("positivitet", VARNING,
                      f"mätningen kommer från flera apparater de senaste {HISTORY_DAYS} dagarna {counts}; "
                      "använd en apparat under hela studien och skriv vilken i design.foljsamhet")]
    return []


def _expected_valid_pairs(pairs: int, valid_rate: float, analysed_days: int) -> int:
    period_ok = 1 - (1 - valid_rate) ** analysed_days
    return math.floor(pairs * period_ok ** 2)


def _pairs_needed(pairs: int, rate: float, analysed: int, effect: float, sd: float, alpha: float) -> int | None:
    """Fewest pairs with power >= MIN_POWER after expected data loss, by bisection (power rises with pairs)."""
    def enough(k: int) -> bool:
        return n1.power(_expected_valid_pairs(k, rate, analysed), effect, sd, alpha, n_sim=POWER_SIMS) >= MIN_POWER
    lo, hi = pairs, MAX_PAIRS_SEARCHED
    if not enough(hi):
        return None
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (lo, mid) if enough(mid) else (mid, hi)
    return hi


def _check_power(study: st.Study, con) -> list[Check]:
    spec, d = study.spec, study.design
    alpha = 1 - spec["analys"].get("niva", 0.95)
    pairs = d["par"]
    analysed = d["periodlangd_dagar"] - d.get("tvatt_dagar", 0)
    out = []
    p_min = 2 / 2 ** pairs
    if p_min > alpha:
        out.append(Check("underlag", STOPP, f"{pairs} par ger minsta möjliga p {p_min:.4f}, över {alpha:.2f}"))
    daily, col = st._daily_outcome(study, con)
    daily = _recent(daily, SD_HISTORY_DAYS)
    if daily.empty:
        return [*out, Check("styrka", STOPP, "ingen glukoshistorik att skatta variationen från")]
    strata, _ = _strata(d)
    wd = set().union(*(s for _, s in strata))
    end = daily["reading_date"].max()
    calendar = [end - timedelta(days=i) for i in range(SD_HISTORY_DAYS) if (end - timedelta(days=i)).weekday() in wd]
    in_stratum = daily[pd.to_datetime(daily["reading_date"]).dt.day_of_week.isin(wd)]
    valid = in_stratum[in_stratum["is_valid_day"] == True][col].dropna()
    rate = len(valid) / len(calendar) if calendar else 0.0
    k_eff = _expected_valid_pairs(pairs, rate, analysed)
    out.append(Check("underlag", VARNING if rate < 0.8 else OK,
                     f"{rate:.0%} av de tillåtna dagarna de senaste {SD_HISTORY_DAYS} dagarna hade giltigt utfall; "
                     f"väntat antal kompletta par {k_eff} av {pairs}"))
    if k_eff < 1 or 2 / 2 ** k_eff > alpha:
        out.append(Check("underlag", STOPP, f"med väntat bortfall ({k_eff} par) kan testet inte nå p ≤ {alpha:.2f}; "
                                            "öka design.par"))
        return out
    basis = "tillåtna dagar"
    if len(valid) < MIN_SD_DAYS:
        # Too few eligible days of history (one weekday gives 13 in 90 days): pool all days.
        valid = daily[daily["is_valid_day"] == True][col].dropna()
        basis = "alla dagar, för få tillåtna"
        if len(valid) < MIN_SD_DAYS:
            out.append(Check("styrka", VARNING, f"bara {len(valid)} giltiga dagar att skatta variationen från; "
                                                "styrkan kan inte bedömas"))
            return out
        out.append(Check("styrka", VARNING, "variationen skattas på alla dagar eftersom de tillåtna är för få; "
                                            "skiljer sig dagstyperna åt i variation blir styrkan fel"))
    sd = float(valid.std(ddof=1)) if analysed == 1 else n1.period_sd(daily, col, analysed)
    effect = abs(spec["analys"]["minsta_relevanta_effekt"])
    pw = n1.power(k_eff, effect, sd, alpha, n_sim=POWER_SIMS)
    text = (f"periodens SD {sd:.2f} (egen data, {basis}); styrka {pw:.0%} att upptäcka "
            f"{effect:g} med {k_eff} kompletta par")
    if pw >= MIN_POWER:
        return [*out, Check("styrka", OK, text)]
    need = _pairs_needed(pairs, rate, analysed, effect, sd, alpha)
    advice = (f"; ungefär {need} par behövs" if need else
              f"; inte ens {MAX_PAIRS_SEARCHED} par räcker: välj ett utfall närmare mekanismen (kortare fönster) "
              "eller gör studien till en skattning och säg det i tesen")
    return [*out, Check("styrka", STOPP, text + advice)]


def _check_data(con) -> list[Check]:
    if data_version(con)["synthetic"]:
        return [Check("data", STOPP, "granskningen kördes på syntetisk demodata; siffrorna säger inget om dig. "
                                     "Kör mot data/selvra.duckdb")]
    return []


# --- observation checks ------------------------------------------------------------------------

def _check_observation(study: st.Study, con) -> list[Check]:
    daily, col = st._daily_outcome(study, con)
    s = st._observation_series(study, daily, col)
    n_exp, n_cmp = st._observation_counts(s)
    floor = study.spec["analys"].get("minsta_underlag", {})
    out = []
    short = n_exp < floor.get("exponerade", st.MIN_DAYS) or n_cmp < floor.get("jamforelse", st.MIN_DAYS)
    retro = study.design.get("retrospektiv", False)
    out.append(Check("underlag", STOPP if short and retro else VARNING if short else OK,
                     f"{n_exp} exponerade och {n_cmp} jämförelsedagar med giltigt utfall nu; "
                     f"studien kräver {floor.get('exponerade')} och {floor.get('jamforelse')}"
                     + (" och datan finns redan, så den kommer att vägras" if short and retro else "")))
    valid = s[s["y"].notna() & s["exposed"].notna()]
    weekend = pd.Series(valid.index.day_of_week.isin(WEEKEND), index=valid.index)
    if valid["exposed"].any() and (~valid["exposed"].astype(bool)).any():
        share_exp = weekend[valid["exposed"] == True].mean()
        share_cmp = weekend[valid["exposed"] == False].mean()
        gap = abs(share_exp - share_cmp)
        level = STOPP if gap > DAYTYPE_STOP else VARNING if gap > DAYTYPE_WARN else OK
        advice = {STOPP: "; exponeringen följer dagstypen och skillnaden går inte att skilja från arbetsdag mot "
                         "ledig. Gör ett n1-försök med design.dagar i stället",
                  VARNING: "; dagstypen kan förklara skillnaden, jämför inom dagstyp", OK: ""}[level]
        out.append(Check("dagtyp", level, f"helgandel {share_exp:.0%} bland exponerade mot {share_cmp:.0%} "
                                          f"bland jämförelsedagar{advice}"))
    return out


# --- Review ------------------------------------------------------------------------------------

def review(study: st.Study, con, today: date | None = None) -> dict:
    today = today or date.today()
    spec, d = study.spec, study.design
    checks = _check_data(con)
    if study.kind == "n1":
        checks += _check_structure(d)
        checks += _check_time(d, today)
        if "verkan" in d:
            checks += _check_order(spec)
            checks += _check_carryover(spec)
        checks += _check_positivity(spec, con)
        checks += _check_power(study, con)
    else:
        checks += _check_observation(study, con)
    return {
        "study": spec["id"],
        "reviewed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "spec_sha256": st._sha(study.path),
        "data_fingerprint": data_version(con)["fingerprint"],
        "verdict": _verdict(checks),
        "checks": [asdict(c) for c in checks],
    }


def render(result: dict) -> str:
    lines = [f"Designgranskning {result['study']}: {result['verdict']}", ""]
    lines += [f"  {c['level']:<7} {c['id']:<12} {c['text']}" for c in result["checks"]]
    if result["verdict"] == STOPP:
        lines += ["", "Låsning vägras tills alla STOPP är åtgärdade i studiefilen."]
    elif result["verdict"] == VARNING:
        lines += ["", "Låsning tillåten. Varje VARNING ska vara bemött i studiefilen (protokoll eller motivering)."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("studie", type=Path)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "selvra.duckdb")
    args = parser.parse_args(argv)
    try:
        study = st.load(args.studie.resolve())
        if study.lock_path.exists():
            raise st.StudyError("studien är redan låst; granskningen gäller utkast")
        with duckdb.connect(str(args.db), read_only=True) as con:
            result = review(study, con)
    except st.StudyError as err:
        print(f"Stopp: {err}", file=sys.stderr)
        return 2
    (study.folder / st.REVIEW_FILE).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(render(result))
    return 1 if result["verdict"] == STOPP else 0


if __name__ == "__main__":
    sys.exit(main())
