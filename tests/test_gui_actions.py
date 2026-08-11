import unittest

from client.controller import ClientController
from client.gui_actions import (
    build_blocker_mapping,
    dispatch_gui_action,
    parse_blockers,
    parse_mana,
)
from client.state_store import ClientStateStore


class RecordingSender:
    def __init__(self):
        self.sent = []

    def send(self, pdu):
        self.sent.append(pdu)


class GuiActionTests(unittest.TestCase):
    def setUp(self):
        self.sender = RecordingSender()
        self.store = ClientStateStore()
        self.store.last_server_seq = 40
        self.store.priority_token = 41
        self.controller = ClientController("p1", self.sender, self.store)

    def test_parses_mana_and_blocker_inputs(self):
        self.assertEqual(parse_mana("R=1, generic=2"), {"R": 1, "X": 2})
        self.assertEqual(
            parse_blockers("goblin_guide_001=ornithopter_001,air_elemental_001"),
            {"goblin_guide_001": ["ornithopter_001", "air_elemental_001"]},
        )

    def test_invalid_structured_input_names_the_recovery(self):
        with self.assertRaisesRegex(ValueError, "COLOR=COUNT"):
            parse_mana("R")
        with self.assertRaisesRegex(ValueError, "ATTACKER=BLOCKER"):
            parse_blockers("goblin_guide_001")

    def test_dispatches_every_gui_game_action_through_controller(self):
        actions = [
            ("keep", ["island_001"], {}, "MULLIGAN_CHOICE"),
            ("mulligan", [], {}, "MULLIGAN_CHOICE"),
            ("pass_priority", [], {}, "PRIORITY_PASS"),
            ("play_land", ["mountain_001"], {}, "PLAY_LAND"),
            ("cast_spell", ["lightning_bolt_001"], {"targets": "p2", "mana": "R=1"}, "CAST_SPELL"),
            ("activate_ability", ["prodigal_sorcerer_001"], {"ability_index": "0", "targets": "p2", "cost": "prodigal_sorcerer_001"}, "ACTIVATE_ABILITY"),
            ("declare_attackers", ["goblin_guide_001"], {}, "DECLARE_ATTACKERS"),
            ("declare_blockers", [], {"assignments": "goblin_guide_001=ornithopter_001"}, "DECLARE_BLOCKERS"),
            ("assign_damage_order", ["goblin_guide_001"], {"order": "ornithopter_001,air_elemental_001"}, "ASSIGN_DAMAGE_ORDER"),
            ("trigger_order", [], {"order": "trigger_2,trigger_1"}, "TRIGGER_ORDER_RESPONSE"),
            ("trigger_choice", [], {"trigger_id": "trigger_1", "accept": True, "target": "p2"}, "TRIGGER_CHOICE_RESPONSE"),
            ("discard", ["shock_001"], {}, "DISCARD"),
            ("concede", [], {}, "CONCEDE"),
        ]

        for action, selected, fields, expected_type in actions:
            with self.subTest(action=action):
                pdu = dispatch_gui_action(self.controller, action, selected, fields)
                self.assertEqual(pdu["type"], expected_type)
                self.assertIs(self.sender.sent[-1], pdu)

        cast = self.sender.sent[4]
        self.assertEqual(cast["targets"], ["p2"])
        self.assertEqual(cast["mana_payment"], {"R": 1})
        blockers = self.sender.sent[7]
        self.assertEqual(blockers["blockers"], {"goblin_guide_001": ["ornithopter_001"]})

    def test_dispatch_rejects_missing_selection_before_sending(self):
        with self.assertRaisesRegex(ValueError, "Select one card"):
            dispatch_gui_action(self.controller, "play_land", [], {})
        self.assertEqual(self.sender.sent, [])

    def test_dispatch_accepts_gui_selected_blockers_and_damage_order(self):
        dispatch_gui_action(
            self.controller,
            "declare_blockers",
            (),
            {"blockers": {"attacker_001": ["blocker_001", "blocker_002"]}},
        )
        dispatch_gui_action(
            self.controller,
            "assign_damage_order",
            ["attacker_001"],
            {"order_ids": ["blocker_002", "blocker_001"]},
        )

        self.assertEqual(self.sender.sent[-2]["blockers"],
                         {"attacker_001": ["blocker_001", "blocker_002"]})
        self.assertEqual(self.sender.sent[-1]["blocker_order"],
                         ["blocker_002", "blocker_001"])

    def test_blocker_mapping_requires_an_explicit_attacker_for_every_blocker(self):
        with self.assertRaisesRegex(ValueError, "Choose an attacker"):
            build_blocker_mapping(
                ["blocker_001", "blocker_002"],
                ["attacker_001", None],
            )

        self.assertEqual(
            build_blocker_mapping(
                ["blocker_001", "blocker_002"],
                ["attacker_002", "attacker_002"],
            ),
            {"attacker_002": ["blocker_001", "blocker_002"]},
        )


if __name__ == "__main__":
    unittest.main()
