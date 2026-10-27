"""Morgonvyn: ett mätinstrument, en sida, renderad av morgonloopen.

Allt motorn vet samlat: gårdagens glukos (Dexcom-klass kurva), senaste domar
med tolkning, vad som är närmast ett svar, motorns minne och det enda som
kräver människan. Skrivs till dashboard/index.html — git-ignorerad, eftersom
den innehåller hälsodata.

Usage:
    uv run python -m selvra_analysis.morgonvy
    make dashboard
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb
import yaml

from selvra_analysis.prioritera import lasta_studier, rankade_hypoteser, utkast

DB_DEFAULT = Path("data/selvra.duckdb")
UT = Path("dashboard/index.html")
STUDIES = Path("studies")

LOW, HIGH = 3.9, 10.0
VERDIKT = {"obestämt": ("UNDETERMINED", "var(--accent)"),
           "håller": ("HOLDS", "#4ade80"),
           "motbevisad": ("REFUTED", "#f87171")}


# --- Data -------------------------------------------------------------------------------------

def _dag(con) -> date | None:
    return con.execute("select max(reading_date) from marts.mart_analysis_days "
                       "where is_valid_day").fetchone()[0]


def _stats(con, d: date) -> dict | None:
    df = con.execute("select tir_pct, tar_pct, tbr_pct, mean_mmol, cv_pct, n_readings, "
                     "sleep_score, steps from marts.mart_analysis_days "
                     "where reading_date = ?", [d]).df()
    return df.iloc[0].to_dict() if len(df) else None


def _kurva(con, d: date) -> list[tuple[float, float]]:
    df = con.execute(
        "select extract(hour from reading_at_local) * 60 + extract(minute from reading_at_local) "
        "as minut, glucose_mmol from intermediate.int_cgm_readings "
        "where reading_date = ? order by reading_at_local", [d]).df()
    return list(zip(df["minut"], df["glucose_mmol"], strict=True))


def _natt(con, d: date) -> float | None:
    r = con.execute(
        "select avg(glucose_mmol) from intermediate.int_cgm_readings "
        "where reading_date = ? and extract(hour from reading_at_local) < 6", [d]).fetchone()[0]
    return round(r, 1) if r is not None else None


def _trend(con, dagar: int = 14) -> list[tuple[str, float]]:
    df = con.execute(
        "select reading_date, tir_pct from marts.mart_analysis_days "
        "where is_valid_day order by reading_date desc limit ?", [dagar]).df()
    return [(str(r.reading_date), float(r.tir_pct)) for r in df.itertuples()][::-1]


AGP_DAGAR = 14
ZONER = (("Mycket högt", "> 13,9", "tar_level2", "#f97316", "< 5%"),
         ("Högt", "10,1–13,9", "tar_level1", "#fdba74", "< 25%"),
         ("I mål", "3,9–10,0", "tir", "#4ade80", "> 70%"),
         ("Lågt", "3,0–3,8", "tbr_level1", "#f87171", "< 4%"),
         ("Mycket lågt", "< 3,0", "tbr_level2", "#dc2626", "< 1%"))


def _agp_band(con) -> list[dict]:
    """Percentiler per halvtimme över de senaste 14 dagarna — AGP-standardens kurva."""
    return con.execute(
        "with b as (select cast((extract(hour from reading_at_local) * 60 "
        "+ extract(minute from reading_at_local)) / 30 as integer) as bin, glucose_mmol "
        "from intermediate.int_cgm_readings where reading_date > "
        "(select max(reading_date) - ? from marts.mart_analysis_days)) "
        "select bin, quantile_cont(glucose_mmol, 0.05) as p05, "
        "quantile_cont(glucose_mmol, 0.25) as p25, median(glucose_mmol) as p50, "
        "quantile_cont(glucose_mmol, 0.75) as p75, quantile_cont(glucose_mmol, 0.95) as p95 "
        "from b group by bin order by bin", [AGP_DAGAR]).df().to_dict("records")


def _agp_stats(con) -> dict:
    """Poolade 14-dagarsmått enligt konsensus: medel, GMI, CV, aktiv tid, fem zoner."""
    r = con.execute(
        "with p as (select glucose_mmol from intermediate.int_cgm_readings "
        "where reading_date > (select max(reading_date) - ? from marts.mart_analysis_days)) "
        "select count(*) as n, avg(glucose_mmol) as medel, "
        "stddev_samp(glucose_mmol) / avg(glucose_mmol) * 100 as cv, "
        "100.0 * count(*) filter (where glucose_mmol > 13.9) / count(*) as tar_level2, "
        "100.0 * count(*) filter (where glucose_mmol > 10.0 and glucose_mmol <= 13.9) / count(*) as tar_level1, "
        "100.0 * count(*) filter (where glucose_mmol >= 3.9 and glucose_mmol <= 10.0) / count(*) as tir, "
        "100.0 * count(*) filter (where glucose_mmol >= 3.0 and glucose_mmol < 3.9) / count(*) as tbr_level1, "
        "100.0 * count(*) filter (where glucose_mmol < 3.0) / count(*) as tbr_level2 "
        "from p", [AGP_DAGAR]).df().iloc[0].to_dict()
    mgdl = r["medel"] * 18.016
    r["gmi"] = 3.31 + 0.02392 * mgdl
    r["aktiv"] = min(100.0, 100.0 * r["n"] / (AGP_DAGAR * 288))
    return r


def _sista_dagar(con, n: int = 7) -> dict[str, list[tuple[float, float]]]:
    df = con.execute(
        "select reading_date, extract(hour from reading_at_local) * 60 "
        "+ extract(minute from reading_at_local) as minut, glucose_mmol "
        "from intermediate.int_cgm_readings where reading_date > "
        "(select max(reading_date) - ? from marts.mart_analysis_days) "
        "order by reading_date, minut", [n]).df()
    ut: dict[str, list[tuple[float, float]]] = {}
    for r in df.itertuples():
        ut.setdefault(str(r.reading_date), []).append((float(r.minut), float(r.glucose_mmol)))
    return ut


def _domar() -> list[dict]:
    ut = []
    for mapp in sorted(STUDIES.glob("[0-9][0-9][0-9]-*"), reverse=True):
        if "exempel" in mapp.name or not (mapp / "slutrapport.md").exists():
            continue
        runs = sorted((mapp / "korningar").glob("*.json"))
        if not runs:
            continue
        rec = json.loads(runs[-1].read_text())
        spec = yaml.safe_load((mapp / "studie.yml").read_text())
        tolk = (mapp / "tolkning.md")
        ut.append({
            "id": mapp.name,
            "fraga": spec.get("fraga", ""),
            "beslut": str(rec.get("beslut", "")).split(":")[0].strip(),
            "est": rec["result"].get("estimate"),
            "lo": rec["result"].get("ci_low"),
            "hi": rec["result"].get("ci_high"),
            "n": f"{rec['result'].get('n_exposed', '?')} mot {rec['result'].get('n_comparison', '?')}",
            "tolkning": tolk.read_text().strip() if tolk.exists() else "",
        })
    return ut


def _minne() -> tuple[list[dict], list[str]]:
    p = STUDIES / "minne.yml"
    if not p.exists():
        return [], []
    data = yaml.safe_load(p.read_text()) or {}
    return data.get("studier", []), data.get("oppna_hypoteser") or []


# --- SVG --------------------------------------------------------------------------------------

def _y(v: float, h: int = 240) -> float:
    lo, hi = 2.0, 22.0
    v = min(max(v, lo), hi)
    return h - (v - lo) / (hi - lo) * h


def _svg_kurva(punkter: list[tuple[float, float]]) -> str:
    w, h = 1000, 240
    delar = [f'<svg viewBox="0 0 {w} {h + 26}" class="kurva" preserveAspectRatio="none">']
    delar.append(f'<rect x="0" y="{_y(HIGH):.0f}" width="{w}" '
                 f'height="{_y(LOW) - _y(HIGH):.0f}" fill="rgba(74,222,128,0.07)"/>')
    for g in (LOW, HIGH):
        delar.append(f'<line x1="0" y1="{_y(g):.0f}" x2="{w}" y2="{_y(g):.0f}" '
                     'stroke="rgba(255,255,255,0.14)" stroke-dasharray="5 6"/>')
    for g, et in ((4, "4"), (10, "10"), (15, "15"), (20, "20")):
        delar.append(f'<text x="6" y="{_y(g) - 5:.0f}" class="ax">{et}</text>')
    for m, et in ((0, "00"), (360, "06"), (720, "12"), (1080, "18"), (1430, "24")):
        delar.append(f'<text x="{m / 1440 * w:.0f}" y="{h + 20}" class="ax">{et}</text>')
    if punkter:
        vag = " ".join(f"{m / 1440 * w:.1f},{_y(g):.1f}" for m, g in punkter)
        delar.append(f'<polyline points="{vag}" fill="none" '
                     'stroke="rgba(250,250,250,0.35)" stroke-width="1.2"/>')
        for m, g in punkter:
            farg = "#f87171" if g < LOW else ("var(--accent)" if g > HIGH else "#fafafa")
            delar.append(f'<circle cx="{m / 1440 * w:.1f}" cy="{_y(g):.1f}" r="2.1" '
                         f'fill="{farg}"/>')
    delar.append("</svg>")
    return "".join(delar)


def _tir_bar(tbr: float, tir: float, tar: float) -> str:
    seg = []
    x = 0.0
    for andel, farg in ((tbr, "#f87171"), (tir, "#4ade80"), (tar, "var(--accent)")):
        if andel and andel > 0:
            seg.append(f'<rect x="{x:.1f}%" y="0" width="{andel:.1f}%" height="14" '
                       f'rx="3" fill="{farg}"/>')
            x += andel
    return ('<svg class="tirbar" viewBox="0 0 100 14" preserveAspectRatio="none">'
            + "".join(seg) + "</svg>")


def _spark(trend: list[tuple[str, float]]) -> str:
    if not trend:
        return ""
    w, h, bw = 238, 40, 14
    delar = [f'<svg viewBox="0 0 {w} {h}" class="spark">']
    for i, (_, v) in enumerate(trend):
        bh = max(2.0, v / 100 * h)
        farg = "#4ade80" if v >= 70 else ("var(--accent)" if v >= 40 else "#f87171")
        delar.append(f'<rect x="{i * (bw + 3)}" y="{h - bh:.0f}" width="{bw}" '
                     f'height="{bh:.0f}" rx="2" fill="{farg}" opacity="0.85"/>')
    delar.append("</svg>")
    return "".join(delar)


def _band_polygon(band: list[dict], lo_k: str, hi_k: str, w: int) -> str:
    n = len(band)
    fram = [f"{(b['bin'] + 0.5) / 48 * w:.1f},{_y(b[hi_k]):.1f}" for b in band]
    bak = [f"{(b['bin'] + 0.5) / 48 * w:.1f},{_y(b[lo_k]):.1f}" for b in reversed(band)]
    return " ".join(fram + bak) if n else ""


def _svg_agp(band: list[dict]) -> str:
    w, h = 1000, 250
    delar = [f'<svg viewBox="0 0 {w} {h + 26}" class="kurva" preserveAspectRatio="none">']
    delar.append(f'<rect x="0" y="{_y(HIGH):.0f}" width="{w}" '
                 f'height="{_y(LOW) - _y(HIGH):.0f}" fill="rgba(74,222,128,0.06)"/>')
    for g in (LOW, HIGH):
        delar.append(f'<line x1="0" y1="{_y(g):.0f}" x2="{w}" y2="{_y(g):.0f}" '
                     'stroke="rgba(74,222,128,0.35)" stroke-dasharray="5 6"/>')
    if band:
        delar.append(f'<polygon points="{_band_polygon(band, "p05", "p95", w)}" '
                     'fill="rgba(255,255,255,0.07)"/>')
        delar.append(f'<polygon points="{_band_polygon(band, "p25", "p75", w)}" '
                     'fill="rgba(255,92,10,0.22)"/>')
        median = " ".join(f"{(b['bin'] + 0.5) / 48 * w:.1f},{_y(b['p50']):.1f}" for b in band)
        delar.append(f'<polyline points="{median}" fill="none" stroke="#fafafa" '
                     'stroke-width="2.4" stroke-linejoin="round"/>')
    for g, et in ((4, "4"), (10, "10"), (15, "15"), (20, "20")):
        delar.append(f'<text x="6" y="{_y(g) - 5:.0f}" class="ax">{et}</text>')
    for m, et in ((0, "00"), (360, "06"), (720, "12"), (1080, "18"), (1400, "24")):
        delar.append(f'<text x="{m / 1440 * w:.0f}" y="{h + 20}" class="ax">{et}</text>')
    delar.append("</svg>")
    return "".join(delar)


def _zonstapel(s: dict) -> str:
    h = 230
    delar = [f'<svg viewBox="0 0 70 {h}" class="zonbar">']
    y = 0.0
    for _, _, nyckel, farg, _ in ZONER:
        andel = max(float(s.get(nyckel) or 0), 0)
        hh = andel / 100 * h
        if hh > 0.5:
            delar.append(f'<rect x="0" y="{y:.1f}" width="26" height="{max(hh, 2):.1f}" '
                         f'fill="{farg}" rx="2"/>')
        y += hh
    delar.append("</svg>")
    rader = "".join(
        f'<div class="zonrad"><span class="zonprick" style="background:{farg}"></span>'
        f'<span class="zonnamn">{namn} <span class="dim">{omr}</span></span>'
        f'<span class="zonpct">{float(s.get(nyckel) or 0):.0f}%</span>'
        f'<span class="zonmal dim">{mal}</span></div>'
        for namn, omr, nyckel, farg, mal in ZONER)
    return f'<div class="zonwrap">{"".join(delar)}<div class="zonlista">{rader}</div></div>'


def _miniatyrer(dagar: dict[str, list[tuple[float, float]]]) -> str:
    kort = []
    for datum, punkter in sorted(dagar.items())[-7:]:
        w, h = 140, 44
        vag = " ".join(f"{m / 1440 * w:.1f},{_y(g, h):.1f}" for m, g in punkter)
        kort.append(
            f'<div class="mini"><svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<rect x="0" y="{_y(HIGH, h):.1f}" width="{w}" '
            f'height="{_y(LOW, h) - _y(HIGH, h):.1f}" fill="rgba(74,222,128,0.08)"/>'
            f'<polyline points="{vag}" fill="none" stroke="rgba(250,250,250,0.8)" '
            f'stroke-width="1.1"/></svg>'
            f'<span class="ax">{datum[5:]}</span></div>')
    return '<div class="minirad">' + "".join(kort) + "</div>"


# --- Sektioner --------------------------------------------------------------------------------

def _sek_agp(con) -> str:
    band = _agp_band(con)
    if not band:
        return ""
    s = _agp_stats(con)
    return f"""
<section class="kort hero-kort">
  <div class="kort-rubrik"><h2>AGP · {AGP_DAGAR} dagar</h2>
  <div class="agp-matt mono dim">aktiv CGM {s['aktiv']:.0f}% · medel {s['medel']:.1f} mmol/L ·
  GMI {s['gmi']:.1f}% · CV {s['cv']:.0f}%</div></div>
  <div class="agp-grid">
    <div>{_svg_agp(band)}</div>
    {_zonstapel(s)}
  </div>
  {_miniatyrer(_sista_dagar(con))}
</section>"""


def _sek_igar(con, d: date) -> str:
    s = _stats(con, d)
    if not s:
        return '<section class="kort"><h2>Igår</h2><p class="dim">Ingen giltig dag ännu.</p></section>'
    natt = _natt(con, d)
    somn = f"{s['sleep_score']:.0f}" if s.get("sleep_score") == s.get("sleep_score") and s.get("sleep_score") is not None else "–"
    steg = f"{s['steps']:,.0f}".replace(",", " ") if s.get("steps") == s.get("steps") and s.get("steps") is not None else "–"
    return f"""
<section class="kort hero-kort">
  <div class="kort-rubrik"><h2>Igår · {d}</h2><div class="spark-wrap">{_spark(_trend(con))}<span class="ax">TIR {AGP_DAGAR} dagar</span></div></div>
  {_svg_kurva(_kurva(con, d))}
  {_tir_bar(s['tbr_pct'], s['tir_pct'], s['tar_pct'])}
  <div class="matris">
    <div><span class="num">{s['tir_pct']:.0f}%</span><span class="et">TIR 3,9–10</span></div>
    <div><span class="num">{s['mean_mmol']:.1f}</span><span class="et">medel mmol/L</span></div>
    <div><span class="num">{natt if natt is not None else '–'}</span><span class="et">natt 00–06</span></div>
    <div><span class="num">{s['cv_pct']:.0f}%</span><span class="et">CV</span></div>
    <div><span class="num">{somn}</span><span class="et">sömnpoäng</span></div>
    <div><span class="num">{steg}</span><span class="et">steg</span></div>
  </div>
</section>"""


def _sek_domar() -> str:
    domar = _domar()
    if not domar:
        return '<section class="kort"><h2>Domar</h2><p class="dim">Ingen studie har körts ännu.</p></section>'
    rader = []
    for dm in domar[:3]:
        et, farg = VERDIKT.get(dm["beslut"], (dm["beslut"].upper(), "var(--dim)"))
        ci = (f"{dm['est']:+.2f} mmol/L · 95% KI [{dm['lo']:+.2f}, {dm['hi']:+.2f}] · {dm['n']} nätter"
              if dm["est"] is not None else "")
        rader.append(f"""
  <article class="dom">
    <div class="dom-topp"><span class="badge" style="color:{farg};border-color:{farg}">{et}</span>
    <span class="mono dim">{dm['id']}</span></div>
    <p class="fraga">{dm['fraga']}</p>
    <p class="mono ci">{ci}</p>
    {f'<p class="tolk">{dm["tolkning"]}</p>' if dm["tolkning"] else ''}
  </article>""")
    return '<section class="kort"><h2>Domar</h2>' + "".join(rader) + "</section>"


def _sek_narmast(con) -> str:
    lagen = lasta_studier(con)
    vant = utkast()
    hyp = rankade_hypoteser(con)
    rader = []
    for lage in lagen[:4]:
        status = "redo att köras" if not lage["saknas"] else "saknas: " + "; ".join(lage["saknas"])
        rader.append(f'<li><span class="mono">{lage["id"]}</span> — {lage["underlag"]}<br>'
                     f'<span class="dim">{status}</span></li>')
    for namn in vant[:3]:
        rader.append(f'<li><span class="mono">{namn}</span> — utkast: '
                     '<span class="dim">kör granska, lås sedan</span></li>')
    for fraga, n in hyp[:3]:
        u = f"{n} dagar underlag" if n is not None else "underlag okänt"
        rader.append(f'<li class="dim">({u}) {fraga}</li>')
    inner = "<ul>" + "".join(rader) + "</ul>" if rader else '<p class="dim">Tomt.</p>'
    return f'<section class="kort"><h2>Närmast ett svar</h2>{inner}</section>'


def _sek_minne() -> str:
    studier, hyp = _minne()
    rader = [f'<li><span class="mono">{s.get("id", "?")}</span> · {s.get("beslut", "?")}'
             + (f'<br><span class="dim">{s["lardom"]}</span>' if s.get("lardom") else "")
             + "</li>"
             for s in studier if "exempel" not in str(s.get("id", ""))]
    if hyp:
        rader.append(f'<li class="dim">{len(hyp)} öppna hypoteser i kö</li>')
    inner = "<ul>" + "".join(rader) + "</ul>" if rader else '<p class="dim">Tomt ännu.</p>'
    return f'<section class="kort"><h2>Motorn vet</h2>{inner}</section>'


def _sek_gora(con) -> str:
    rader = []
    for namn in utkast():
        rader.append(f"<li>Granska och lås <span class='mono'>{namn}</span></li>")
    wearable = con.execute("select count(*) from marts.mart_analysis_days "
                           "where wearable_source is not null").fetchone()[0]
    if wearable == 0:
        rader.append("<li>Synka klockan — ingen wearable-data i marten ännu</li>")
    rader.append("<li><span class='mono'>make dagbok</span> — gårdagens ja/nej (30 sekunder)</li>")
    return ('<section class="kort"><h2>Kräver dig</h2><ul>' + "".join(rader)
            + "</ul></section>")


# --- Sida -------------------------------------------------------------------------------------

CSS = """
:root{--bg:#000;--yta:rgba(255,255,255,0.025);--kant:rgba(255,255,255,0.07);
--kant2:rgba(255,255,255,0.14);--fg:#fafafa;--dim:#8a8a92;--svag:#4a4a52;--accent:#ff5c0a}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:'Geist',-apple-system,sans-serif;
font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;
background-image:radial-gradient(rgba(255,255,255,0.045) 1px,transparent 1px);background-size:28px 28px}
.wrap{max-width:1080px;margin:0 auto;padding:36px 24px 64px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}
.logo{display:flex;align-items:center;gap:10px;font-weight:600;font-size:17px}
.logo svg{width:24px;height:24px}
.datum{font-family:'Geist Mono',monospace;font-size:12px;color:var(--dim)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.hero-kort{grid-column:1/-1}
.kort{background:var(--yta);border:1px solid var(--kant);border-radius:16px;padding:22px 24px}
.kort h2{font-size:13px;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;
color:var(--dim);margin-bottom:14px}
.kort-rubrik{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap}
.spark-wrap{display:flex;align-items:center;gap:10px}
.spark{width:170px;height:30px}
.kurva{width:100%;height:230px;margin:6px 0 10px}
.ax{font-family:'Geist Mono',monospace;font-size:10px;fill:var(--svag)}
.tirbar{width:100%;height:12px;border-radius:4px;margin-bottom:16px}
.matris{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}
.matris div{display:flex;flex-direction:column}
.num{font-size:26px;font-weight:600;letter-spacing:-0.02em}
.et{font-family:'Geist Mono',monospace;font-size:10.5px;color:var(--svag);margin-top:2px}
.agp-grid{display:grid;grid-template-columns:1fr 290px;gap:22px;align-items:start}
.agp-matt{font-size:12px}
.zonwrap{display:flex;gap:14px;align-items:stretch}
.zonbar{width:30px;height:230px;flex-shrink:0}
.zonlista{display:flex;flex-direction:column;justify-content:space-between;padding:2px 0;flex:1}
.zonrad{display:grid;grid-template-columns:10px 1fr auto auto;gap:8px;align-items:center;
font-size:12px}
.zonprick{width:9px;height:9px;border-radius:3px;display:inline-block}
.zonnamn .dim{font-family:'Geist Mono',monospace;font-size:10.5px}
.zonpct{font-weight:600;font-size:14px;text-align:right}
.zonmal{font-family:'Geist Mono',monospace;font-size:10px}
.minirad{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;margin-top:16px}
.mini{display:flex;flex-direction:column;gap:3px}
.mini svg{width:100%;height:40px;background:rgba(255,255,255,0.02);border:1px solid var(--kant);
border-radius:6px}
.mini .ax{font-size:9.5px;color:var(--svag);font-family:'Geist Mono',monospace}
.dom{border-top:1px solid var(--kant);padding:13px 0}
.dom:first-of-type{border-top:0;padding-top:2px}
.dom-topp{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.badge{font-family:'Geist Mono',monospace;font-size:11px;border:1px solid;border-radius:999px;
padding:2px 10px}
.fraga{font-size:14.5px;margin-bottom:4px}
.ci{font-size:12px;color:var(--dim)}
.tolk{font-size:13px;color:var(--dim);margin-top:8px;border-left:2px solid var(--kant2);
padding-left:10px}
.mono{font-family:'Geist Mono',monospace;font-size:12.5px}
.dim{color:var(--dim)}
ul{list-style:none}
li{padding:7px 0;border-top:1px solid var(--kant);font-size:14px}
li:first-child{border-top:0}
footer{margin-top:28px;font-family:'Geist Mono',monospace;font-size:11px;color:var(--svag);
display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
a{color:var(--dim)}
@media(max-width:760px){.grid{grid-template-columns:1fr}.matris{grid-template-columns:repeat(3,1fr)}
.num{font-size:21px}.agp-grid{grid-template-columns:1fr}.minirad{grid-template-columns:repeat(4,1fr)}}
"""

MARKE = ('<svg viewBox="0 0 32 32" fill="none"><path d="M6.5 11 V21 M25.5 11 V21 M6.5 16 H25.5" '
         'stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>'
         '<circle cx="16" cy="16" r="3.2" fill="#ff5c0a"/></svg>')


def render(db_path: Path) -> str:
    with duckdb.connect(str(db_path), read_only=True) as con:
        d = _dag(con)
        agp = _sek_agp(con) if d else ""
        igar = _sek_igar(con, d) if d else '<section class="kort"><p class="dim">Ingen data.</p></section>'
        narmast = _sek_narmast(con)
        gora = _sek_gora(con)
    nu = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Selvra · morgonvy</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><div class="wrap">
<header><div class="logo">{MARKE}Selvra <span class="dim" style="font-weight:400">· morgonvy</span></div>
<div class="datum">renderad {nu}</div></header>
<div class="grid">
{agp}
{igar}
{_sek_domar()}
{narmast}
{_sek_minne()}
{gora}
</div>
<footer><span>varje siffra kommer ur motorns körjournaler och databasen</span>
<span><a href="datahalsa.html">datahälsa →</a></span></footer>
</div></body></html>"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = parser.parse_args(argv)
    UT.parent.mkdir(exist_ok=True)
    UT.write_text(render(args.db))
    print(f"Morgonvyn: {UT}", file=sys.stderr)


if __name__ == "__main__":
    main()
