"""Rörloggen: varje hämtning bokförs med version och form — innan någon frågar.

Mätlagrets (METODPLAN §6) råmaterial: en append-bar logg över varje datahämtning
— vilken enhet, vilken firmware, vilket bibliotek, vilka fält, hur många rader.
Drift upptäcks genom att jämföra loggen med sig själv över tid; en historik som
den här går inte att återskapa i efterhand, så den börjar nu.

En rad JSON per hämtning i data/rorlogg.jsonl (gitignorerat som allt i data/).
Loggen beskriver rören, aldrig människorna: inga mätvärden, bara form.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

LOGG = Path("data/rorlogg.jsonl")


def logga(kalla: str, person: str, **form) -> dict:
    """Bokför en hämtning: bibliotek, enhet, firmware, dagar, rader, falt.
    Returnerar raden (för test och loggutskrift)."""
    rad = {
        "tid": datetime.now(UTC).isoformat(timespec="seconds"),
        "kalla": kalla, "person": person,
        "bibliotek": str(form.get("bibliotek", "")),
        "enhet": str(form.get("enhet", "")),
        "firmware": str(form.get("firmware", "")),
        "dagar": int(form.get("dagar", 0)), "rader": int(form.get("rader", 0)),
        "falt": sorted(form.get("falt") or []),
    }
    LOGG.parent.mkdir(parents=True, exist_ok=True)
    with LOGG.open("a") as f:
        f.write(json.dumps(rad, ensure_ascii=False) + "\n")
    return rad


def enhetsinfo(garmin) -> tuple[str, str]:
    """Modell och firmware; get_devices bär firmware (get_device_last_used gör det inte).

    Firmware per hämtning är fellogg-dimensionens nyckel: mjukvaruversioner
    flyttar mått flera procent inom samma person (Sturrock m.fl. 2025), och
    drift som träffar fil och API lika syns bara som förändringspunkter vid
    kända versionsbyten. Tomt vid fel, aldrig stopp."""
    try:
        enheter = garmin.get_devices() or []
        d = enheter[0] if enheter else {}
        return (str(d.get("productDisplayName", "")),
                str(d.get("currentFirmwareVersion", "")))
    except Exception:  # noqa: BLE001 — loggen får aldrig fälla hämtningen
        return "", ""
