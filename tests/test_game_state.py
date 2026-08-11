import random
import unittest

from server.game_state import GameState, Lifecycle, Phase, PermanentState, StackItem


class GameStateTests(unittest.TestCase):
    def setUp(self):
        self.state = GameState.new(
            ("player_1", "player_2"),
            {"player_1": [f"mountain_{i:03d}" for i in range(1, 11)],
             "player_2": [f"island_{i:03d}" for i in range(1, 11)]},
            "player_1", random.Random(4),
        )

    def test_new_game_sets_twenty_life_and_seven_card_hands(self):
        self.assertEqual(self.state.lifecycle, Lifecycle.MULLIGAN)
        self.assertEqual(self.state.players["player_1"].life, 20)
        self.assertEqual(len(self.state.players["player_1"].hand), 7)
        self.assertEqual(len(self.state.players["player_2"].library), 3)

    def test_visible_state_hides_opponent_hand_and_both_libraries(self):
        view = self.state.visible_to("player_1")
        self.assertEqual(view["life_totals"], {"player_1": 20, "player_2": 20})
        self.assertEqual(set(view["hand"]), {"player_1"})
        self.assertNotIn("library", view)
        self.assertEqual(view["hand_counts"]["player_2"], 7)
        self.assertFalse(view["land_played_this_turn"])

    def test_visible_state_contains_public_permanent_and_stack_data(self):
        self.state.players["player_1"].battlefield.append(
            PermanentState("goblin_guide_001", "player_1", "player_1", tapped=True))
        self.state.stack.append(StackItem("stk_1", "SPELL", "lightning_bolt_001",
                                          "player_1", ["player_2"]))
        view = self.state.visible_to("player_2")
        self.assertEqual(view["battlefield"]["player_1"][0]["id"], "goblin_guide_001")
        self.assertEqual(view["stack"][0]["stack_item_id"], "stk_1")

    def test_short_deck_draws_only_available_opening_cards(self):
        state = GameState.new(("a", "b"), {"a": ["mountain_001"],
                                            "b": ["island_001", "island_002"]},
                              "a", random.Random(1))
        self.assertEqual(len(state.players["a"].hand), 1)
        self.assertEqual(len(state.players["b"].hand), 2)


if __name__ == "__main__":
    unittest.main()
