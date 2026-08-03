import unittest

from server.game_state import StackItem
from server.priority_stack import PriorityError, PriorityOutcome, PriorityStack


class PriorityStackTests(unittest.TestCase):
    def setUp(self):
        self.priority = PriorityStack("player_1", "player_2")

    def test_two_passes_resolve_nonempty_stack_then_return_priority_to_active_player(self):
        self.priority.open("player_1", 10)
        self.priority.push(StackItem("stk_1", "SPELL", "lightning_bolt_001",
                                     "player_1", ["player_2"]))
        self.assertEqual(self.priority.pass_priority("player_1", 10), PriorityOutcome.TRANSFER)
        self.priority.grant("player_2", 11)
        self.assertEqual(self.priority.pass_priority("player_2", 11), PriorityOutcome.RESOLVE_TOP)
        self.assertEqual(self.priority.holder, "player_1")

    def test_two_passes_on_empty_stack_advance_step(self):
        self.priority.open("player_1", 2)
        self.priority.pass_priority("player_1", 2)
        self.priority.grant("player_2", 3)
        self.assertEqual(self.priority.pass_priority("player_2", 3), PriorityOutcome.ADVANCE_STEP)

    def test_action_resets_passes_and_keeps_priority(self):
        self.priority.open("player_1", 4)
        self.priority.act("player_1", 4)
        self.assertEqual(self.priority.holder, "player_1")
        self.assertEqual(self.priority.consecutive_passes, 0)

    def test_stale_token_and_wrong_holder_are_distinct_errors(self):
        self.priority.open("player_1", 4)
        with self.assertRaises(PriorityError) as stale:
            self.priority.act("player_1", 3)
        self.assertEqual(stale.exception.code, "STALE_ACTION")
        with self.assertRaises(PriorityError) as wrong:
            self.priority.act("player_2", 4)
        self.assertEqual(wrong.exception.code, "NOT_YOUR_PRIORITY")

    def test_stack_is_last_in_first_out(self):
        self.priority.push(StackItem("one", "SPELL", "a", "player_1"))
        self.priority.push(StackItem("two", "SPELL", "b", "player_2"))
        self.assertEqual(self.priority.pop().stack_item_id, "two")


if __name__ == "__main__":
    unittest.main()
