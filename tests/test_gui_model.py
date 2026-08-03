import unittest
from pathlib import Path

from client.gui_model import (
    CardCatalog,
    GameView,
    GuiEventBridge,
    available_actions,
    base_card_id,
    legal_target_options,
)


ROOT = Path(__file__).resolve().parents[1]


class GuiModelTests(unittest.TestCase):
    def test_catalog_resolves_instance_id_to_supplied_card(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")

        card = catalog.card("lightning_bolt_003")

        self.assertEqual(base_card_id("lightning_bolt_003"), "lightning_bolt")
        self.assertEqual(card.name, "Lightning Bolt")
        self.assertEqual(card.card_type, "Instant")

    def test_game_view_uses_only_public_opponent_counts(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        state = self._state()

        view = GameView.from_state("p1", state, catalog)

        self.assertEqual(view.player.hand_count, 2)
        self.assertEqual([card.name for card in view.hand], ["Mountain", "Lightning Bolt"])
        self.assertEqual(view.opponent.hand_count, 4)
        self.assertFalse(hasattr(view.opponent, "hand"))
        self.assertEqual(view.opponent.library_count, 35)

    def test_game_view_derives_phase_priority_and_permanent_state(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")

        view = GameView.from_state("p1", self._state(), catalog)

        self.assertEqual(view.phase_label, "Pre-combat main")
        self.assertTrue(view.has_priority)
        self.assertTrue(view.is_active_player)
        self.assertEqual(view.player.battlefield[0].name, "Mountain")
        self.assertTrue(view.player.battlefield[0].tapped)

    def test_event_bridge_drains_callbacks_in_posted_order(self):
        bridge = GuiEventBridge()
        seen = []
        bridge.post(seen.append, "state")
        bridge.post(seen.append, "event")

        drained = bridge.drain()

        self.assertEqual(drained, 2)
        self.assertEqual(seen, ["state", "event"])
        self.assertEqual(bridge.drain(), 0)

    def test_event_bridge_reports_one_bad_callback_and_continues(self):
        bridge = GuiEventBridge()
        seen = []
        errors = []
        bridge.post(lambda: (_ for _ in ()).throw(RuntimeError("broken callback")))
        bridge.post(seen.append, "later state")

        drained = bridge.drain(errors.append)

        self.assertEqual(drained, 2)
        self.assertEqual(seen, ["later state"])
        self.assertEqual(str(errors[0]), "broken callback")

    def test_available_actions_hide_unsupported_and_wrong_phase_controls(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        state = self._state()
        state["land_played"] = {"p1": False, "p2": False}
        view = GameView.from_state("p1", state, catalog)

        self.assertIn("play_land", available_actions(view, ["mountain_001"]))
        self.assertIn("cast_spell", available_actions(view, ["lightning_bolt_003"]))
        self.assertNotIn("activate_ability", available_actions(view, ["mountain_002"]))

        state["hand"]["p1"] = ["shock_001"]
        unsupported = GameView.from_state("p1", state, catalog)
        self.assertNotIn("cast_spell", available_actions(unsupported, ["shock_001"]))

        state["phase"] = "UPKEEP"
        wrong_phase = GameView.from_state("p1", state, catalog)
        self.assertNotIn("play_land", available_actions(wrong_phase, ["mountain_001"]))
        self.assertNotIn("discard", available_actions(wrong_phase, ["shock_001"]))

    def test_legal_target_options_are_derived_from_authoritative_state(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        state = self._state()
        state["battlefield"]["p2"] = [{
            "card_id": "ornithopter_001", "owner": "p2", "controller": "p2",
            "tapped": False, "summoning_sick": False, "damage": 0,
            "power_modifier": 0, "toughness_modifier": 0,
        }]
        state["stack"] = [{"stack_item_id": "stk_4", "item_type": "SPELL",
                           "source": "shock_001", "controller": "p2", "targets": ["p1"]}]
        view = GameView.from_state("p1", state, catalog)

        bolt_targets = dict(legal_target_options(view, catalog.card("lightning_bolt_003")))
        counter_targets = dict(legal_target_options(view, catalog.card("counterspell_001")))
        growth_targets = dict(legal_target_options(view, catalog.card("giant_growth_001")))

        self.assertIn("p2", bolt_targets)
        self.assertIn("ornithopter_001", bolt_targets)
        self.assertEqual(set(counter_targets), {"stk_4"})
        self.assertEqual(set(growth_targets), {"ornithopter_001"})

    @staticmethod
    def _state():
        return {
            "lifecycle": "PLAYING",
            "phase": "PRECOMBAT_MAIN",
            "turn": 3,
            "first_player": "p1",
            "active_player": "p1",
            "priority_holder": "p1",
            "priority_token": 18,
            "life_totals": {"p1": 20, "p2": 17},
            "hand": {"p1": ["mountain_001", "lightning_bolt_003"]},
            "hand_counts": {"p1": 2, "p2": 4},
            "library_counts": {"p1": 34, "p2": 35},
            "land_played": {"p1": False, "p2": False},
            "battlefield": {
                "p1": [{"card_id": "mountain_002", "owner": "p1", "controller": "p1",
                         "tapped": True, "summoning_sick": False, "damage": 0,
                         "power_modifier": 0, "toughness_modifier": 0}],
                "p2": [],
            },
            "graveyard": {"p1": [], "p2": ["shock_001"]},
            "exile": {"p1": [], "p2": []},
            "stack": [],
            "combat": {"attackers": [], "blockers": {}, "damage_order": {}},
        }


if __name__ == "__main__":
    unittest.main()
