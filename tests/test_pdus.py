import unittest

from common.pdus import (
    CLIENT_TO_SERVER_TYPES,
    ERROR_CODES,
    PDU_DIRECTIONS,
    PDU_TYPES,
    SERVER_TO_CLIENT_TYPES,
    PDUValidationError,
    validate_pdu,
)


EXPECTED = {
    "PLAYER_READY", "GAME_STATE_UPDATE", "MULLIGAN_CHOICE", "PHASE_TRANSITION",
    "PRIORITY_GRANT", "PRIORITY_PASS", "CAST_SPELL", "ACTIVATE_ABILITY",
    "STACK_PUSH", "TRIGGER_ORDER", "TRIGGER_ORDER_RESPONSE", "TRIGGER_CHOICE",
    "TRIGGER_CHOICE_RESPONSE", "STACK_RESOLVE", "DECLARE_ATTACKERS",
    "DECLARE_BLOCKERS", "ASSIGN_DAMAGE_ORDER", "COMBAT_DAMAGE_RESULT",
    "PLAY_LAND", "DISCARD", "CONCEDE", "GAME_OVER", "ERROR", "PING", "PONG",
}


class PDUContractTests(unittest.TestCase):
    def test_registry_contains_exactly_the_25_rfc_types(self):
        self.assertEqual(PDU_TYPES, EXPECTED)
        self.assertEqual(set(PDU_DIRECTIONS), EXPECTED)

    def test_every_pdu_requires_type_and_integer_seq_num(self):
        with self.assertRaisesRegex(PDUValidationError, "seq_num"):
            validate_pdu({"type": "PRIORITY_PASS"}, direction="C->S")
        with self.assertRaises(PDUValidationError):
            validate_pdu({"type": "PRIORITY_PASS", "seq_num": True}, direction="C->S")

    def test_direction_mismatch_is_unknown_type(self):
        with self.assertRaises(PDUValidationError) as raised:
            validate_pdu({"type": "GAME_OVER", "seq_num": 2,
                          "winner_id": "p1", "loser_id": "p2", "reason": "LIFE_ZERO"},
                         direction="C->S")
        self.assertEqual(raised.exception.code, "UNKNOWN_TYPE")

    def test_required_fields_are_enforced(self):
        with self.assertRaises(PDUValidationError) as raised:
            validate_pdu({"type": "PLAY_LAND", "seq_num": 3}, direction="C->S")
        self.assertEqual(raised.exception.code, "ILLEGAL_ACTION")

    def test_validation_returns_copy(self):
        original = {"type": "PING", "seq_num": 3, "timestamp": 9.0}
        result = validate_pdu(original, direction="C->S")
        self.assertEqual(result, original)
        self.assertIsNot(result, original)

    def test_direction_sets_cover_broadcasts_for_server(self):
        self.assertIn("PLAYER_READY", CLIENT_TO_SERVER_TYPES)
        self.assertIn("PHASE_TRANSITION", SERVER_TO_CLIENT_TYPES)
        self.assertNotIn("PHASE_TRANSITION", CLIENT_TO_SERVER_TYPES)

    def test_error_code_registry_is_exact(self):
        self.assertEqual(ERROR_CODES, {
            "INVALID_JSON", "ILLEGAL_DECK", "UNKNOWN_TYPE", "STALE_ACTION",
            "NOT_YOUR_PRIORITY", "ILLEGAL_ACTION", "ILLEGAL_TARGET",
            "TRIGGER_ORDER_INVALID", "TRIGGER_CHOICE_INVALID", "INSUFFICIENT_MANA",
            "WRONG_PHASE", "DUPLICATE_ID",
        })


if __name__ == "__main__":
    unittest.main()
