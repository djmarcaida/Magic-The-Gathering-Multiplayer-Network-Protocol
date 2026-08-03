import unittest
from pathlib import Path

from common.cards import CardCatalog, DeckValidationError


ROOT = Path(__file__).parents[1]


class CardCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CardCatalog.from_json(ROOT / "cards.json")

    def test_catalog_matches_supplied_totals(self):
        self.assertEqual(len(self.catalog.definitions), 58)
        self.assertEqual(len(self.catalog.instances), 312)

    def test_lightning_bolt_uses_supplied_card_values(self):
        bolt = self.catalog.get("lightning_bolt_001")
        self.assertEqual((bolt.card_type, bolt.colors, bolt.mana_cost),
                         ("Instant", ("R",), {"R": 1}))
        self.assertEqual(bolt.effect, "Lightning Bolt deals 3 damage to any target.")

    def test_gray_merchant_has_two_black_devotion_symbols(self):
        merchant = self.catalog.get("gray_merchant_004")
        self.assertEqual(merchant.mana_cost, {"B": 2, "generic": 3})
        self.assertEqual((merchant.power, merchant.toughness), (2, 4))

    def test_instance_ids_use_three_digit_copy_suffix(self):
        self.assertTrue(self.catalog.contains("mountain_020"))
        self.assertFalse(self.catalog.contains("mountain_021"))

    def test_deck_rejects_unknown_duplicate_empty_and_over_fifty(self):
        for deck in ([], ["nope_001"], ["mountain_001"] * 2,
                     list(self.catalog.instances)[:51]):
            with self.subTest(deck_length=len(deck)):
                with self.assertRaises(DeckValidationError):
                    self.catalog.validate_deck(deck)

    def test_deck_accepts_one_to_fifty_distinct_supplied_instances(self):
        deck = list(self.catalog.instances)[:50]
        self.assertEqual(self.catalog.validate_deck(deck), tuple(deck))


if __name__ == "__main__":
    unittest.main()
