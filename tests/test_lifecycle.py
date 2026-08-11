import copy
import unittest

from server.game_state import Lifecycle, Phase
from tests.helpers import BLUE_DECK, RED_DECK, make_engine, ready, start_engine


class LifecycleTests(unittest.TestCase):
    def test_two_valid_ready_pdus_start_personalized_mulligan(self):
        engine = make_engine()
        first = engine.process("seat_1", ready("player_1", RED_DECK))
        self.assertEqual(first[-1].pdu["state"]["lifecycle"], "LOBBY")
        outgoing = engine.process("seat_2", ready("player_2", BLUE_DECK))
        updates = [m for m in outgoing if m.pdu["type"] == "GAME_STATE_UPDATE"]
        self.assertEqual(engine.state.lifecycle, Lifecycle.MULLIGAN)
        self.assertEqual({m.recipient for m in updates}, {"seat_1", "seat_2"})
        p1 = next(x.pdu["state"] for x in updates if x.recipient == "seat_1")
        self.assertNotIn("player_2", p1["hand"])

    def test_duplicate_id_and_illegal_deck_are_recoverable(self):
        engine = make_engine()
        engine.process("seat_1", ready("same", RED_DECK))
        duplicate = engine.process("seat_2", ready("same", BLUE_DECK))
        self.assertEqual(duplicate[0].pdu["code"], "DUPLICATE_ID")
        illegal = engine.process("seat_2", ready("other", []))
        self.assertEqual(illegal[0].pdu["code"], "ILLEGAL_DECK")
        self.assertIsNone(engine.state)

    def test_both_keeps_run_untap_automatically_then_open_upkeep_priority(self):
        engine = start_engine()
        for seat in ("seat_1", "seat_2"):
            token = engine.request_tokens[seat]
            outgoing = engine.process(seat, {"type": "MULLIGAN_CHOICE", "seq_num": token,
                                             "keep": True, "cards_to_bottom": []})
        self.assertEqual(engine.state.lifecycle, Lifecycle.PLAYING)
        self.assertEqual((engine.state.turn, engine.state.phase), (1, Phase.UPKEEP))
        transitions = [x.pdu["to_phase"] for x in outgoing
                       if x.pdu["type"] == "PHASE_TRANSITION"]
        self.assertEqual(transitions, ["UNTAP", "UPKEEP"])
        grants = [x.pdu for x in outgoing if x.pdu["type"] == "PRIORITY_GRANT"]
        self.assertEqual([x["player_id"] for x in grants], [engine.state.active_player])

    def test_priority_grant_follows_the_first_post_keep_snapshot(self):
        engine = start_engine()
        for seat in ("seat_1", "seat_2"):
            token = engine.request_tokens[seat]
            outgoing = engine.process(seat, {"type": "MULLIGAN_CHOICE", "seq_num": token,
                                             "keep": True, "cards_to_bottom": []})
        holder = engine.state.active_player
        holder_seat = engine.seat_for_player(holder)
        grant = next(x.pdu for x in outgoing
                     if x.pdu["type"] == "PRIORITY_GRANT" and x.recipient == holder_seat)
        self.assertEqual(grant["player_id"], holder)
        self.assertEqual(grant["seq_num"], engine.request_tokens[holder_seat])

    def test_first_post_keep_snapshot_has_upkeep_priority_not_untap_priority(self):
        engine = start_engine()
        for seat in ("seat_1", "seat_2"):
            token = engine.request_tokens[seat]
            engine.process(seat, {"type": "MULLIGAN_CHOICE", "seq_num": token,
                                  "keep": True, "cards_to_bottom": []})
        self.assertEqual(engine.state.phase, Phase.UPKEEP)
        self.assertEqual(engine.state.turn, 1)

    def test_invalid_priority_action_reissues_the_same_priority_token(self):
        engine = start_engine()
        for seat in ("seat_1", "seat_2"):
            engine.process(seat, {"type": "MULLIGAN_CHOICE",
                                  "seq_num": engine.request_tokens[seat],
                                  "keep": True, "cards_to_bottom": []})
        holder = engine.state.priority_holder
        seat = engine.seat_for_player(holder)
        token = engine.request_tokens[seat]

        outgoing = engine.process(seat, {"type": "CAST_SPELL", "seq_num": token,
                                         "card_id": "not_in_hand", "targets": [],
                                         "mana_payment": {}})

        self.assertEqual(outgoing[0].pdu["type"], "ERROR")
        retry = outgoing[-1].pdu
        self.assertEqual((retry["type"], retry["seq_num"], retry["player_id"]),
                         ("PRIORITY_GRANT", token, holder))

    def test_mulligan_rerolls_and_requires_bottom_count_on_keep(self):
        engine = start_engine()
        player = engine.state.players[engine.player_for_seat("seat_1")]
        before = list(player.hand)
        token = engine.request_tokens["seat_1"]
        engine.process("seat_1", {"type": "MULLIGAN_CHOICE", "seq_num": token,
                                  "keep": False, "cards_to_bottom": []})
        self.assertEqual(player.mulligans, 1)
        self.assertEqual(len(player.hand), 7)
        token = engine.request_tokens["seat_1"]
        snapshot = copy.deepcopy(player.hand)
        error = engine.process("seat_1", {"type": "MULLIGAN_CHOICE", "seq_num": token,
                                          "keep": True, "cards_to_bottom": []})
        self.assertEqual(error[0].pdu["code"], "ILLEGAL_ACTION")
        self.assertEqual(player.hand, snapshot)
        bottom = [player.hand[0]]
        engine.process("seat_1", {"type": "MULLIGAN_CHOICE", "seq_num": token,
                                  "keep": True, "cards_to_bottom": bottom})
        self.assertEqual(len(player.hand), 6)
        self.assertIn(bottom[0], player.library[:1])
        self.assertNotEqual(before, player.hand)

    def test_concede_sends_game_over_then_returns_to_lobby(self):
        engine = start_engine()
        loser = engine.player_for_seat("seat_1")
        winner = engine.state.opponent_of(loser)
        outgoing = engine.process("seat_1", {"type": "CONCEDE", "seq_num": 99,
                                              "player_id": loser})
        game_over = next(x.pdu for x in outgoing if x.pdu["type"] == "GAME_OVER")
        self.assertEqual((game_over["winner_id"], game_over["reason"]), (winner, "CONCEDE"))
        self.assertIsNone(engine.state)

    def test_ping_is_echoed_as_pong(self):
        engine = make_engine()
        result = engine.process("seat_1", {"type": "PING", "seq_num": 8, "timestamp": 4.5})
        self.assertEqual(result[0].pdu, {"type": "PONG", "seq_num": 8, "timestamp": 4.5})

    def test_same_id_ready_resynchronizes_reserved_seat_and_wrong_id_is_rejected(self):
        engine = start_engine()
        expected_id = engine.player_for_seat("seat_1")
        deck = RED_DECK if expected_id == "player_1" else BLUE_DECK
        resync = engine.process("seat_1", ready(expected_id, deck, seq=20))
        self.assertEqual(resync[0].pdu["type"], "GAME_STATE_UPDATE")
        wrong = engine.process("seat_1", ready("intruder", deck, seq=21))
        self.assertEqual(wrong[0].pdu["type"], "ERROR")


if __name__ == "__main__":
    unittest.main()
