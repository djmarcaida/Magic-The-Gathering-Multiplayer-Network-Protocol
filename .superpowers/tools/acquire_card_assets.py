from __future__ import annotations

import io
import json
import time
import urllib.request
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "client" / "assets" / "cards"
HEADERS = {
    "User-Agent": "MTGNP-Student-Client/1.0",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}


def fetch_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


cards = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
response = fetch_json(
    "https://api.scryfall.com/cards/collection",
    {"identifiers": [{"name": card["name"]} for card in cards]},
)
by_name = {item["name"].casefold(): item for item in response["data"]}
missing = [card["name"] for card in cards if card["name"].casefold() not in by_name]
if missing:
    raise SystemExit(f"Scryfall did not match: {missing}")

OUT.mkdir(parents=True, exist_ok=True)
manifest = {}
for index, card in enumerate(cards, 1):
    remote = by_name[card["name"].casefold()]
    image_url = remote["image_uris"]["png"]
    source = fetch_bytes(image_url)
    with Image.open(io.BytesIO(source)) as image:
        resized = image.convert("RGBA").resize((240, 335), Image.Resampling.LANCZOS)
        resized.save(OUT / f"{card['base_id']}.png", format="PNG", optimize=True, compress_level=9)
    manifest[card["base_id"]] = {
        "card_name": card["name"],
        "scryfall_id": remote["id"],
        "artist": remote.get("artist") or "Unknown",
        "source_page": remote["scryfall_uri"],
        "image_source": image_url,
    }
    print(f"[{index:02d}/{len(cards)}] {card['name']}")
    time.sleep(0.05)

(OUT / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
