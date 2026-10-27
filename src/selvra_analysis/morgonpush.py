"""Morgonrapporten som pushnotis till telefonen, via webbsidan i web/morgon.

Rapporten är densamma som morgonmejlet (morgonmejl.compose). Den skickas krypterad direkt
till telefonen (Web Push); webbsidan sparar den bara i telefonen. Ingen server lagrar den.

En gång, på datorn som skickar:
    uv run python -m selvra_analysis.morgonpush nycklar          # nyckelpar; committa web/morgon/config.js
En gång per telefon (koden kommer från sidan när notiserna slagits på):
    uv run python -m selvra_analysis.morgonpush koppla pappa KOD
Varje morgon:
    uv run python -m selvra_analysis.morgonpush skicka pappa      # hämta ny data och skicka
    uv run python -m selvra_analysis.morgonpush visa pappa        # visa vad som skulle skickas

Den privata nyckeln ligger i data/push/ (gitignored) och lämnar aldrig datorn.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import date
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

from selvra_analysis.forslag import forslagsrad
from selvra_analysis.ingest_garmin import load as load_garmin
from selvra_analysis.ingest_garmin import person_paths
from selvra_analysis.morgonmejl import FETCH_DAYS, compose, read_days

KEY_DIR = Path("data/push")
PRIVATE_KEY = KEY_DIR / "vapid_private.pem"
PUBLIC_CONFIG = Path("web/morgon/config.js")
CONTACT = "mailto:hello@selvra.ai"
SHORT_MAX = 170           # what a lock-screen notification shows


def _public_key_b64(v: Vapid01) -> str:
    raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_keys(force: bool = False) -> str:
    if PRIVATE_KEY.exists() and not force:
        raise SystemExit(f"{PRIVATE_KEY} finns redan. Nya nycklar kopplar bort alla telefoner; använd --ny om du menar det.")
    v = Vapid01()
    v.generate_keys()
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    v.save_key(str(PRIVATE_KEY))
    public = _public_key_b64(v)
    PUBLIC_CONFIG.write_text("// Publik nyckel för morgonnotiser (den privata ligger bara på datorn som skickar)\n"
                             f'window.SELVRA_VAPID_PUBLIC = "{public}";\n')
    return public


def connect(person: str, code: str) -> Path:
    """Store the phone's push subscription, from the code the page shows (base64 JSON, or JSON)."""
    text = code.strip()
    try:
        sub = json.loads(text)
    except json.JSONDecodeError:
        sub = json.loads(base64.b64decode(text + "=" * (-len(text) % 4)).decode())
    if not sub.get("endpoint") or not (sub.get("keys") or {}).get("p256dh"):
        raise SystemExit("koden är inte en giltig push-prenumeration")
    out = person_paths(person)["db"].parent / "push.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sub))
    return out


def payload(subject: str, body: str, today: date) -> dict:
    """Title, the short lock-screen text, and the full report for the page."""
    facts = [line[2:] for line in body.splitlines() if line.startswith("- ")]
    warning = next((line for line in body.splitlines()[1:4] if "synkat" in line), None)
    short = warning or " · ".join(f.split(", ")[0].replace("Garmin ", "") for f in facts) or "Ingen ny data i natt."
    return {"titel": subject, "kort": short[:SHORT_MAX], "text": body, "datum": f"{today.day}/{today.month}"}


def send(person: str, data: dict) -> None:
    sub_path = person_paths(person)["db"].parent / "push.json"
    if not sub_path.exists():
        raise SystemExit(f"{person} har ingen kopplad telefon: kör `morgonpush koppla {person} KOD`")
    if not PRIVATE_KEY.exists():
        raise SystemExit("nycklarna saknas: kör `morgonpush nycklar`")
    try:
        webpush(subscription_info=json.loads(sub_path.read_text()), data=json.dumps(data, ensure_ascii=False),
                vapid_private_key=str(PRIVATE_KEY), vapid_claims={"sub": CONTACT}, ttl=12 * 3600)
    except WebPushException as err:
        status = getattr(err.response, "status_code", None)
        if status in (404, 410):
            raise SystemExit(f"telefonen har avregistrerat notiserna; öppna Selvra på telefonen, slå på igen "
                             f"och koppla den nya koden ({status})") from err
        raise


def _report(person: str, fetch: bool) -> dict:
    paths = person_paths(person)
    conf = yaml.safe_load((paths["db"].parent / "person.yml").read_text())
    if fetch:
        load_garmin(paths["db"], FETCH_DAYS, paths["token"], paths["snapshots"])
    today = date.today()
    subject, body = compose(conf["namn"], read_days(paths["db"]), today)
    rad = forslagsrad(person, paths["db"], today, bygg=fetch)
    if rad:
        body = body.rstrip() + "\n\n" + rad + "\n"
    return payload(subject, body, today)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="kommando", required=True)
    k = sub.add_parser("nycklar", help="skapa nyckelpar (en gång)")
    k.add_argument("--ny", action="store_true")
    c = sub.add_parser("koppla", help="koppla en telefon till en person")
    c.add_argument("person")
    c.add_argument("kod")
    for name in ("skicka", "visa"):
        sub.add_parser(name).add_argument("person")
    args = parser.parse_args(argv)
    if args.kommando == "nycklar":
        make_keys(args.ny)
        print(f"Klart. Committa och pusha {PUBLIC_CONFIG} så att sidan får den publika nyckeln.")
    elif args.kommando == "koppla":
        print(f"Kopplad: {connect(args.person, args.kod)}")
    elif args.kommando == "visa":
        d = _report(args.person, fetch=False)
        print(f"Notis: {d['titel']}\n{d['kort']}\n\nPå sidan:\n{d['text']}")
    else:
        d = _report(args.person, fetch=True)
        send(args.person, d)
        print(f"Skickad till {args.person}: {d['titel']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
