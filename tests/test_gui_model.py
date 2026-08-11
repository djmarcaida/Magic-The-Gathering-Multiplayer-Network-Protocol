import unittest
from dataclasses import replace
from pathlib import Path

from client.gui_model import (
    CardCatalog,
    GameView,
    GuiEventBridge,
    PHASE_LABELS,
    available_actions,
    base_card_id,
    bounded_activity_history,
    card_border_color,
    legal_target_options,
    phase_neighbors,
    resource_summary,
)
from server.game_state import Phase


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

    def test_event_bridge_leaves_callbacks_for_the_next_tick_when_bounded(self):
        bridge = GuiEventBridge()
        seen = []
        for value in range(3):
            bridge.post(seen.append, value)

        self.assertEqual(bridge.drain(max_callbacks=2), 2)
        self.assertEqual(seen, [0, 1])
        self.assertEqual(bridge.drain(max_callbacks=2), 1)
        self.assertEqual(seen, [0, 1, 2])

    def test_event_bridge_defaults_to_a_bounded_tick(self):
        bridge = GuiEventBridge()
        seen = []
        for value in range(33):
            bridge.post(seen.append, value)

        self.assertEqual(bridge.drain(), 32)
        self.assertEqual(seen, list(range(32)))
        self.assertEqual(bridge.drain(), 1)
        self.assertEqual(seen, list(range(33)))

    def test_activity_history_retains_only_the_newest_entries(self):
        history = ()
        for value in range(255):
            history = bounded_activity_history(history, f"event {value}", limit=250)

        self.assertEqual(len(history), 250)
        self.assertEqual(history[0], "event 5")
        self.assertEqual(history[-1], "event 254")

    def test_activity_history_flattens_multiline_messages(self):
        history = bounded_activity_history((), "first line\nsecond line", limit=250)

        self.assertEqual(history, ("first line second line",))

    def test_card_border_color_uses_catalog_colors(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        expected = {
            "plains_001": "#F3DF9B",
            "island_001": "#63A8D5",
            "swamp_001": "#997AAF",
            "mountain_001": "#D76A5B",
            "forest_001": "#63AA73",
            "sol_ring_001": "#AFB5B1",
        }
        for card_id, color in expected.items():
            state = self._state()
            state["hand"]["p1"] = [card_id]
            card = GameView.from_state("p1", state, catalog).hand[0]
            with self.subTest(card_id=card_id):
                self.assertEqual(card_border_color(card), color)

        multicolor = replace(card, colors=("R", "G"))
        self.assertEqual(card_border_color(multicolor), "#D5AD49")

    def test_resource_summary_counts_only_untapped_supported_mana_sources(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        state = self._state()
        state["battlefield"]["p1"] = [
            {"id": "mountain_001", "tapped": False},
            {"id": "mountain_002", "tapped": True},
            {"id": "forest_001", "tapped": False},
            {"id": "plains_001", "tapped": False},
            {"id": "island_001", "tapped": False},
            {"id": "swamp_001", "tapped": False},
            {"id": "sol_ring_001", "tapped": False},
            {"id": "llanowar_elves_001", "tapped": False},
        ]
        summary = resource_summary(GameView.from_state("p1", state, catalog).player)

        self.assertEqual(summary.mana_sources,
                         {"R": 1, "G": 1, "W": 1, "U": 1, "B": 1, "C": 2})
        self.assertEqual(summary.permanent_count, 8)
        self.assertEqual(summary.life, 20)
        self.assertEqual(summary.hand_count, 2)
        self.assertEqual(summary.library_count, 34)
        self.assertEqual(summary.graveyard_count, 0)
        self.assertEqual(summary.exile_count, 0)
        self.assertFalse(summary.land_played)

    def test_phase_neighbors_use_the_protocol_phase_order(self):
        self.assertEqual(tuple(PHASE_LABELS), tuple(phase.value for phase in Phase))
        self.assertEqual(
            phase_neighbors("PRECOMBAT_MAIN"),
            ("DRAW", "PRECOMBAT_MAIN", "BEGIN_COMBAT"),
        )
        self.assertEqual(phase_neighbors("UNTAP"), ("CLEANUP", "UNTAP", "UPKEEP"))
        self.assertEqual(phase_neighbors("CLEANUP"), ("END_STEP", "CLEANUP", "UNTAP"))

    def test_available_actions_hide_unsupported_and_wrong_phase_controls(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        state = self._state()
        state["land_played_this_turn"] = False
        view = GameView.from_state("p1", state, catalog)

        self.assertIn("play_land", available_actions(view, ["mountain_001"]))
        self.assertIn("cast_spell", available_actions(view, ["lightning_bolt_003"]))
        self.assertNotIn("activate_ability", available_actions(view, ["mountain_002"]))

        state["priority_holder"] = "p2"
        waiting_for_opponent = GameView.from_state("p1", state, catalog)
        self.assertNotIn("play_land", available_actions(waiting_for_opponent, ["mountain_001"]))
        state["priority_holder"] = "p1"

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
            "id": "ornithopter_001", "owner": "p2", "controller": "p2",
            "tapped": False, "summoning_sickness": False, "damage": 0,
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
            "land_played_this_turn": False,
            "battlefield": {
                "p1": [{"id": "mountain_002", "owner": "p1", "controller": "p1",
                         "tapped": True, "summoning_sickness": False, "damage": 0,
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
