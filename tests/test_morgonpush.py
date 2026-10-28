"""Keys, connecting a phone, the notification text, and encryption to a real subscription key."""

import base64
import json
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPusher

from selvra_analysis import morgonpush as mp


def _subscription() -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return {"endpoint": "https://push.example/abc", "keys": {"p256dh": b64(raw), "auth": b64(b"0123456789abcdef")}}


def test_keys_write_only_the_public_key_to_the_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "web" / "morgon").mkdir(parents=True)
    public = mp.make_keys()
    assert len(base64.urlsafe_b64decode(public + "==")) == 65, "uncompressed P-256 point"
    assert public in (tmp_path / "web/morgon/config.js").read_text()
    assert "PRIVATE" not in (tmp_path / "web/morgon/config.js").read_text()
    assert (tmp_path / "data/push/vapid_private.pem").exists()


def test_the_code_from_the_page_connects_the_phone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    sub = _subscription()
    out = mp.connect("testare-1", base64.b64encode(json.dumps(sub).encode()).decode())
    assert json.loads(out.read_text()) == sub
    assert out.is_relative_to(Path("data/personer/testare-1"))


def test_the_lock_screen_text_is_short_and_the_warning_comes_first() -> None:
    body = ("God morgon Kari,\n\nKlockan har inte synkat sedan 22/10. Öppna Garmin Connect-appen.\n\n"
            "- Garmin räknade 4 100 steg i går, inom ditt vanliga 2 500–5 700.\n\nSelvra\n")
    d = mp.payload("Selvra onsdag 28/10 – klockan har inte synkat", body, date(2026, 10, 28))
    assert d["kort"].startswith("Klockan har inte synkat")
    assert len(d["kort"]) <= mp.SHORT_MAX
    assert d["text"] == body


def test_the_report_encrypts_to_a_real_subscription_key() -> None:
    data = json.dumps(mp.payload("Selvra", "- Garmin räknade 4 100 steg i går.\n", date(2026, 10, 28)))
    encoded = WebPusher(_subscription()).encode(data.encode(), content_encoding="aes128gcm")
    assert encoded["body"]
    assert data.encode() not in encoded["body"]
