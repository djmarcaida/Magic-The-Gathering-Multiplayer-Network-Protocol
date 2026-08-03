import json
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "client" / "assets" / "cards"


class GuiAssetTests(unittest.TestCase):
    def test_every_supplied_card_has_an_optimized_png_and_manifest_record(self):
        cards = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
        manifest = json.loads((ASSET_DIR / "manifest.json").read_text(encoding="utf-8"))

        expected_ids = {card["base_id"] for card in cards}
        self.assertEqual(set(manifest), expected_ids)
        self.assertEqual({path.stem for path in ASSET_DIR.glob("*.png")}, expected_ids)

        for card in cards:
            base_id = card["base_id"]
            image_path = ASSET_DIR / f"{base_id}.png"
            with image_path.open("rb") as image:
                self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
                length = struct.unpack(">I", image.read(4))[0]
                self.assertEqual(image.read(4), b"IHDR")
                width, height = struct.unpack(">II", image.read(length)[:8])
            self.assertEqual((width, height), (240, 335))

            record = manifest[base_id]
            self.assertEqual(record["card_name"], card["name"])
            self.assertTrue(record["scryfall_id"])
            self.assertTrue(record["artist"])
            self.assertTrue(record["source_page"].startswith("https://scryfall.com/card/"))
            self.assertTrue(record["image_source"].startswith("https://cards.scryfall.io/"))


if __name__ == "__main__":
    unittest.main()
