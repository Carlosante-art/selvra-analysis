"""serrier: registret över rören — apparater, firmware, hämtvägar, händelser.

Spårhunden gräver för att säkerställa, inte för att döma. Registret äger bara
händelserna: apparat, firmware, rör, mått, storlek, osäkerhet, antal, datum.
Ingen kolumn kan peka på en person — gränsen bevisas av ett test, inte av
en policy (test_serrier).

Livscykeln är domstolsprincipen som datamodell:

  kandidat    skapas AUTOMATISKT ur rörloggen när något ändrat form
              (firmware, bibliotek, fältlista). Aldrig publik.
  provad      sätts BARA MANUELLT, med kvitto: ett kontrollerat test har
              gjorts — två likadana apparater samma natt, eller samma apparat
              genom två rör — och resultatet har siffra och osäkerhet.
  publicerad  sätts BARA MANUELLT, med kvitto: tillverkaren har fått dagar
              att kommentera; bara aggregat; inga namngivna tredjeparter utan
              skriftligt ok.

Vad detta INTE är: inte ett domslut om kroppar (rörets trohet, aldrig
fysiologisk sanning), inte en fellogg (en kandidat är en observerad
formändring, inte ett konstaterat fel), och inte publikt förrän en post
nått status publicerad genom människohänder.

Sanningen bor i journalen (data/serrier/journal.jsonl, append-only,
gitignorerad, backupad). DuckDB-schemat `serrier` är en återspelning:
`uppdatera` bygger om det från journalen när som helst. Den dag serrier
blir något eget flyttar en mapp, inte en kodbas.

    uv run python -m selvra_analysis.serrier uppdatera   # kandidater ur rörloggen + återspela schema
    uv run python -m selvra_analysis.serrier lista
    uv run python -m selvra_analysis.serrier prova <id> --kvitto "..."
    uv run python -m selvra_analysis.serrier publicera <id> --kvitto "..."

Mer än detta byggs inte förrän det första riktiga firmware-bytet syns i
rörloggen (Carls instruktion 2026-10-29).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

JOURNAL = Path("data/serrier/journal.jsonl")
RORLOGG = Path("data/rorlogg.jsonl")
DB = Path("data/selvra.duckdb")
FORM_FALT = ("firmware", "bibliotek", "enhet", "falt")
STATUS_ORDNING = ["kandidat", "provad", "publicerad"]


def _journal_rader() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(r) for r in JOURNAL.read_text().splitlines() if r.strip()]


def _journal_skriv(rad: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(rad, ensure_ascii=False) + "\n")


def _handelse_id(modell: str, ror: str, beskrivning: str) -> str:
    return hashlib.sha256(f"{modell}|{ror}|{beskrivning}".encode()).hexdigest()[:12]


def kandidater_fran_rorlogg() -> int:
    """Formändringar i rörloggen blir kandidat-händelser. Idempotent: samma
    ändring journalförs aldrig två gånger."""
    if not RORLOGG.exists():
        return 0
    rorlogg = [json.loads(r) for r in RORLOGG.read_text().splitlines() if r.strip()]
    journal = _journal_rader()
    kanda = {r["id"] for r in journal if r.get("op") == "kandidat"}
    sedda_fw = {(r["modell"], r["version"]) for r in journal if r.get("op") == "firmware"}
    senast: dict[tuple, dict] = {}
    nya = 0
    for r in rorlogg:
        modell = r.get("enhet") or "okand"
        if r.get("firmware") and (modell, r["firmware"]) not in sedda_fw:
            _journal_skriv({"op": "firmware", "modell": modell,
                            "version": r["firmware"], "datum": r["tid"][:10]})
            sedda_fw.add((modell, r["firmware"]))
        nyckel = (r.get("kalla"), r.get("enhet") or "okand")
        forra = senast.get(nyckel)
        if forra:
            for falt in FORM_FALT:
                if r.get(falt) == forra.get(falt):
                    continue
                beskrivning = f"{falt}: {forra.get(falt)!r} → {r.get(falt)!r}"
                hid = _handelse_id(str(r.get("enhet")), str(r.get("kalla")), beskrivning)
                if hid in kanda:
                    continue
                _journal_skriv({
                    "op": "kandidat", "id": hid,
                    "datum": r["tid"][:10], "modell": r.get("enhet") or "okand",
                    "ror": r.get("kalla"),
                    "firmware_fore": forra.get("firmware"), "firmware_efter": r.get("firmware"),
                    "beskrivning": beskrivning,
                    "matt": None, "storlek": None, "osakerhet": None, "n": None,
                    "tillverkar_svar": None,
                })
                kanda.add(hid)
                nya += 1
        senast[nyckel] = r
    return nya


def satt_status(hid: str, ny_status: str, kvitto: str) -> None:
    """provad/publicerad sätts bara manuellt, med kvitto, ett steg i taget."""
    if ny_status not in STATUS_ORDNING[1:]:
        raise ValueError(f"okänd status: {ny_status}")
    if not kvitto or not kvitto.strip():
        raise ValueError("statusbyte kräver ett kvitto — det är domarens underskrift")
    nuvarande = status_for(hid)
    if nuvarande is None:
        raise ValueError(f"ingen händelse med id {hid}")
    if STATUS_ORDNING.index(ny_status) != STATUS_ORDNING.index(nuvarande) + 1:
        raise ValueError(f"{nuvarande} → {ny_status} hoppar i trappan; ett steg i taget")
    _journal_skriv({"op": "status", "id": hid, "status": ny_status, "kvitto": kvitto.strip(),
                    "datum": datetime.now(UTC).date().isoformat()})


def status_for(hid: str) -> str | None:
    status = None
    for r in _journal_rader():
        if r.get("id") != hid:
            continue
        if r["op"] == "kandidat":
            status = "kandidat"
        elif r["op"] == "status":
            status = r["status"]
    return status


def uppdatera(db: Path = DB) -> int:
    """Nya kandidater ur rörloggen, sedan återspelas journalen in i schemat."""
    nya = kandidater_fran_rorlogg()
    spela_upp(db)
    return nya


def spela_upp(db: Path = DB) -> None:
    """Journalen → DuckDB-schemat serrier. Schemat är en vy av journalen,
    aldrig tvärtom — därför kan det byggas om när som helst."""
    rader = _journal_rader()
    handelser: dict[str, dict] = {}
    for r in rader:
        if r["op"] == "kandidat":
            handelser[r["id"]] = {**r, "status": "kandidat", "kvitto": None}
        elif r["op"] == "status" and r["id"] in handelser:
            handelser[r["id"]]["status"] = r["status"]
            handelser[r["id"]]["kvitto"] = r["kvitto"]
    with duckdb.connect(str(db)) as con:
        con.execute("create schema if not exists serrier")
        con.execute("create or replace table serrier.apparat (modell varchar, serie varchar)")
        con.execute("create or replace table serrier.firmware "
                    "(modell varchar, version varchar, forst_sedd date)")
        con.execute(
            "create or replace table serrier.handelse (id varchar, datum date, modell varchar, "
            "ror varchar, firmware_fore varchar, firmware_efter varchar, beskrivning varchar, "
            "matt varchar, storlek double, osakerhet double, n integer, "
            "status varchar, kvitto varchar, tillverkar_svar varchar)")
        modeller = sorted({h["modell"] for h in handelser.values()})
        fw_forst: dict[tuple, str] = {}
        for r in rader:
            if r["op"] == "firmware" and (r["modell"], r["version"]) not in fw_forst:
                fw_forst[(r["modell"], r["version"])] = r["datum"]
        for (m, v), d in fw_forst.items():
            con.execute("insert into serrier.firmware values (?, ?, ?)", [m, v, d])
        for m in sorted({m for m, _ in fw_forst} | set(modeller)):
            con.execute("insert into serrier.apparat values (?, null)", [m])
        for h in handelser.values():
            con.execute("insert into serrier.handelse values "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [h["id"], h["datum"], h["modell"], h["ror"],
                         h.get("firmware_fore"), h.get("firmware_efter"), h["beskrivning"],
                         h.get("matt"), h.get("storlek"), h.get("osakerhet"), h.get("n"),
                         h["status"], h.get("kvitto"), h.get("tillverkar_svar")])


def grupperade(idag_journal: list[dict] | None = None) -> list[dict]:
    """Kandidater grupperade över apparater (princip 3 / populationskontrollen):
    en IDENTISK formändring som träffar flera modeller är uppströms — bibliotek,
    API eller pipeline — inte apparaten. Hoppar bara en modell är det apparaten.

    Returnerar en post per unik (beskrivning, datum); omfattning säger hur många
    apparater och om det är uppströms eller apparatspecifikt."""
    rader = idag_journal if idag_journal is not None else _journal_rader()
    status = {}
    for r in rader:
        if r["op"] == "kandidat":
            status[r["id"]] = "kandidat"
        elif r["op"] == "status":
            status[r["id"]] = r["status"]
    grupper: dict[tuple, dict] = {}
    for r in rader:
        if r["op"] != "kandidat":
            continue
        nyckel = (r["beskrivning"], r["datum"])
        g = grupper.setdefault(nyckel, {
            "beskrivning": r["beskrivning"], "datum": r["datum"], "ror": r["ror"],
            "modeller": set(), "ids": [], "statusar": set()})
        g["modeller"].add(r["modell"])
        g["ids"].append(r["id"])
        g["statusar"].add(status.get(r["id"], "kandidat"))
    ut = []
    for g in grupper.values():
        n = len(g["modeller"])
        g["omfattning"] = (f"{n} apparater — UPPSTRÖMS (bibliotek/API/pipeline, inte apparaten)"
                           if n >= 2 else "en apparat (apparatspecifik)")
        g["modeller"] = sorted(g["modeller"])
        ut.append(g)
    return sorted(ut, key=lambda g: (g["datum"], g["beskrivning"]))


def lista() -> str:
    grupper = grupperade()
    if not grupper:
        return "Registret är tomt — inga formändringar observerade ännu."
    rader = []
    for g in grupper:
        status = "/".join(sorted(g["statusar"]))
        rader.append(f"{g['datum']}  {','.join(g['modeller'])}/{g['ror']}  [{status}]  "
                     f"{g['beskrivning'][:70]}")
        rader.append(f"           ↳ {g['omfattning']}")
    return "\n".join(rader)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="kommando", required=True)
    sub.add_parser("uppdatera")
    sub.add_parser("lista")
    for namn in ("prova", "publicera"):
        k = sub.add_parser(namn)
        k.add_argument("id")
        k.add_argument("--kvitto", required=True)
    args = p.parse_args(argv)
    if args.kommando == "uppdatera":
        nya = uppdatera()
        print(f"{nya} nya kandidater; schemat återspelat", file=sys.stderr)
    elif args.kommando == "lista":
        print(lista())
    else:
        satt_status(args.id, "provad" if args.kommando == "prova" else "publicerad", args.kvitto)
        spela_upp(DB)
        print(f"{args.id} → {args.kommando}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
