import unittest

from client.state_store import ClientStateStore
from server.game_state import Phase, PermanentState
from tests.helpers import start_engine


def playing_engine():
    engine = start_engine()
    for seat in ("seat_1", "seat_2"):
        engine.process(seat, {"type": "MULLIGAN_CHOICE",
                              "seq_num": engine.request_tokens[seat],
                              "keep": True, "cards_to_bottom": []})
    return engine


def pass_window(engine):
    first = engine.state.priority_holder
    first_seat = engine.seat_for_player(first)
    engine.process(first_seat, {"type": "PRIORITY_PASS",
                                "seq_num": engine.request_tokens[first_seat]})
    second = engine.state.priority_holder
    second_seat = engine.seat_for_player(second)
    return engine.process(second_seat, {"type": "PRIORITY_PASS",
                                        "seq_num": engine.request_tokens[second_seat]})


class BackendSpecTests(unittest.TestCase):
    def test_priority_transfer_synchronizes_both_client_projections(self):
        engine = playing_engine()
        stores = {seat: ClientStateStore() for seat in ("seat_1", "seat_2")}

        def apply(outgoing):
            for item in outgoing:
                if item.recipient in stores:
                    stores[item.recipient].apply_pdu(item.pdu)

        apply(engine.snapshot_updates())
        previous_holder = engine.state.priority_holder
        previous_seat = engine.seat_for_player(previous_holder)

        apply(engine.process(previous_seat, {
            "type": "PRIORITY_PASS",
            "seq_num": engine.request_tokens[previous_seat],
        }))

        expected_holder = engine.state.opponent_of(previous_holder)
        self.assertEqual(engine.state.priority_holder, expected_holder)
        self.assertEqual(
            {seat: store.state.get("priority_holder") for seat, store in stores.items()},
            {"seat_1": expected_holder, "seat_2": expected_holder},
        )
        self.assertEqual(
            sum(store.state.get("priority_holder") == engine.player_for_seat(seat)
                for seat, store in stores.items()),
            1,
        )

    def test_declaration_steps_wait_for_the_required_player_and_validate_token(self):
        engine = playing_engine()
        pass_window(engine)  # upkeep -> draw
        pass_window(engine)  # draw -> main 1
        pass_window(engine)  # main 1 -> begin combat
        outgoing = pass_window(engine)  # begin combat -> declare attackers request

        self.assertEqual(engine.state.phase, Phase.DECLARE_ATTACKERS)
        self.assertIsNone(engine.state.priority_holder)
        self.assertFalse(any(x.pdu["type"] == "PRIORITY_GRANT" for x in outgoing))
        active_seat = engine.seat_for_player(engine.state.active_player)
        stale = engine.process(active_seat, {"type": "DECLARE_ATTACKERS",
                                             "seq_num": 0, "attackers": []})
        self.assertEqual(stale[0].pdu["code"], "STALE_ACTION")
        self.assertEqual(stale[1].pdu["type"], "GAME_STATE_UPDATE")
        self.assertEqual(engine.request_tokens[active_seat], stale[1].pdu["seq_num"])

    def test_stale_blocker_request_resynchronizes_and_can_be_retried(self):
        engine = playing_engine()
        active = engine.state.active_player
        defender = engine.state.opponent_of(active)
        attacker = PermanentState("goblin_guide_001", active, active,
                                  summoning_sick=False)
        blocker = PermanentState("ornithopter_001", defender, defender,
                                 summoning_sick=False)
        engine.state.players[active].battlefield.append(attacker)
        engine.state.players[defender].battlefield.append(blocker)
        engine.state.phase = Phase.DECLARE_BLOCKERS
        engine.state.combat.attackers = [attacker.card_id]
        defender_seat = engine.seat_for_player(defender)
        engine.request_tokens[defender_seat] = 50

        stale = engine.process(defender_seat, {
            "type": "DECLARE_BLOCKERS", "seq_num": 49,
            "blockers": {attacker.card_id: [blocker.card_id]},
        })
        retry_token = stale[-1].pdu["seq_num"]
        retried = engine.process(defender_seat, {
            "type": "DECLARE_BLOCKERS", "seq_num": retry_token,
            "blockers": {attacker.card_id: [blocker.card_id]},
        })

        self.assertEqual(stale[0].pdu["code"], "STALE_ACTION")
        self.assertEqual(stale[-1].pdu["type"], "GAME_STATE_UPDATE")
        self.assertFalse(any(item.pdu["type"] == "ERROR" for item in retried))
        self.assertEqual(engine.state.combat.blockers,
                         {attacker.card_id: [blocker.card_id]})

    def test_no_attack_skips_to_end_of_combat_and_opens_priority(self):
        engine = playing_engine()
        for _ in range(4):
            pass_window(engine)
        active_seat = engine.seat_for_player(engine.state.active_player)

        outgoing = engine.process(active_seat, {"type": "DECLARE_ATTACKERS",
                                                 "seq_num": engine.request_tokens[active_seat],
                                                 "attackers": []})

        self.assertEqual(engine.state.phase, Phase.END_OF_COMBAT)
        self.assertEqual(engine.state.priority_holder, engine.state.active_player)
        self.assertIn("END_OF_COMBAT", [x.pdu.get("to_phase") for x in outgoing])

    def test_empty_board_completes_a_full_turn_without_stalling(self):
        engine = playing_engine()
        first = engine.state.active_player
        for _ in range(4):
            pass_window(engine)
        active_seat = engine.seat_for_player(first)
        engine.process(active_seat, {"type": "DECLARE_ATTACKERS",
                                     "seq_num": engine.request_tokens[active_seat],
                                     "attackers": []})
        pass_window(engine)  # end combat -> main 2
        pass_window(engine)  # main 2 -> end step
        outgoing = pass_window(engine)  # end step -> cleanup -> next untap -> upkeep

        self.assertEqual((engine.state.turn, engine.state.phase), (2, Phase.UPKEEP))
        self.assertNotEqual(engine.state.active_player, first)
        self.assertEqual([x.pdu.get("to_phase") for x in outgoing
                          if x.pdu["type"] == "PHASE_TRANSITION"],
                         ["CLEANUP", "UNTAP", "UPKEEP"])

    def test_rfc_attack_and_block_shapes_progress_to_automatic_combat_damage(self):
        engine = playing_engine()
        active = engine.state.active_player
        defender = engine.state.opponent_of(active)
        attacker = PermanentState("goblin_guide_001", active, active,
                                  summoning_sick=False)
        blocker = PermanentState("phantasmal_bear_001", defender, defender,
                                 summoning_sick=False)
        engine.state.players[active].battlefield = [attacker]
        engine.state.players[defender].battlefield = [blocker]
        engine.state.phase = Phase.DECLARE_ATTACKERS
        engine.state.priority_holder = None
        a_seat = engine.seat_for_player(active)
        d_seat = engine.seat_for_player(defender)

        engine.process(a_seat, {"type": "DECLARE_ATTACKERS",
                                "seq_num": engine.request_tokens[a_seat],
                                "attackers": [{"creature_id": attacker.card_id,
                                                "target": defender}]})
        pass_window(engine)
        self.assertEqual(engine.state.phase, Phase.DECLARE_BLOCKERS)
        engine.process(d_seat, {"type": "DECLARE_BLOCKERS",
                                "seq_num": engine.request_tokens[d_seat],
                                "blockers": [{"creature_id": blocker.card_id,
                                              "blocking_id": attacker.card_id}]})
        outgoing = pass_window(engine)

        self.assertEqual(engine.state.phase, Phase.END_OF_COMBAT)
        self.assertTrue(any(x.pdu["type"] == "COMBAT_DAMAGE_RESULT" for x in outgoing))
        self.assertIsNone(engine.state.permanent(attacker.card_id))
        self.assertIsNone(engine.state.permanent(blocker.card_id))

    def test_cleanup_never_grants_priority_and_waits_for_active_player_discard(self):
        engine = playing_engine()
        active = engine.state.active_player
        active_seat = engine.seat_for_player(active)
        player = engine.state.players[active]
        while len(player.hand) < 9:
            player.hand.append(f"mountain_{20 - len(player.hand):03d}")
        engine.state.phase = Phase.END_STEP

        outgoing = engine.advance_step()

        self.assertEqual(engine.state.phase, Phase.CLEANUP)
        self.assertIsNone(engine.state.priority_holder)
        self.assertFalse(any(x.pdu["type"] == "PRIORITY_GRANT" for x in outgoing))
        token = engine.request_tokens[active_seat]
        discard = player.hand[:2]
        outgoing = engine.process(active_seat, {"type": "DISCARD", "seq_num": token,
                                                "card_ids": discard})
        self.assertEqual(engine.state.phase, Phase.UPKEEP)
        self.assertEqual(engine.state.turn, 2)
        self.assertEqual(engine.state.priority_holder, engine.state.active_player)
        self.assertEqual([x.pdu.get("to_phase") for x in outgoing
                          if x.pdu["type"] == "PHASE_TRANSITION"],
                         ["UNTAP", "UPKEEP"])

    def test_first_strike_damage_is_conditional_and_opens_its_own_window(self):
        engine = playing_engine()
        active = engine.state.active_player
        defender = engine.state.opponent_of(active)
        attacker = PermanentState("white_knight_001", active, active,
                                  summoning_sick=False)
        blocker = PermanentState("phantasmal_bear_001", defender, defender,
                                 summoning_sick=False)
        engine.state.players[active].battlefield = [attacker]
        engine.state.players[defender].battlefield = [blocker]
        engine.state.phase = Phase.DECLARE_BLOCKERS
        engine.state.combat.attackers = [attacker.card_id]
        engine.state.combat.blockers = {attacker.card_id: [blocker.card_id]}

        outgoing = engine._after_blocker_window()

        self.assertEqual(engine.state.phase, Phase.FIRST_STRIKE_DAMAGE)
        self.assertIsNone(engine.state.permanent(blocker.card_id))
        self.assertEqual(engine.state.priority_holder, active)
        self.assertTrue(any(x.pdu["type"] == "COMBAT_DAMAGE_RESULT" for x in outgoing))
        pass_window(engine)
        self.assertEqual(engine.state.phase, Phase.END_OF_COMBAT)
        self.assertEqual(engine.state.players[defender].life, 20)

    def test_multiple_blockers_require_damage_order_before_damage(self):
        engine = playing_engine()
        active = engine.state.active_player
        defender = engine.state.opponent_of(active)
        attacker = PermanentState("reckless_wurm_001", active, active,
                                  summoning_sick=False)
        blockers = [
            PermanentState("phantasmal_bear_001", defender, defender,
                           summoning_sick=False),
            PermanentState("grizzly_bears_001", defender, defender,
                           summoning_sick=False),
        ]
        engine.state.players[active].battlefield = [attacker]
        engine.state.players[defender].battlefield = list(blockers)
        engine.state.phase = Phase.DECLARE_BLOCKERS
        engine.state.combat.attackers = [attacker.card_id]
        engine.state.combat.blockers = {
            attacker.card_id: [blocker.card_id for blocker in blockers],
        }

        engine._after_blocker_window()

        self.assertEqual(engine.state.phase, Phase.ASSIGN_DAMAGE_ORDER)
        active_seat = engine.seat_for_player(active)
        outgoing = engine.process(active_seat, {
            "type": "ASSIGN_DAMAGE_ORDER",
            "seq_num": engine.request_tokens[active_seat],
            "attacker_id": attacker.card_id,
            "blocker_order": [blocker.card_id for blocker in blockers],
        })
        self.assertEqual(sum(item.pdu["type"] == "PRIORITY_GRANT" for item in outgoing), 1)
        self.assertEqual(sum(item.pdu["type"] == "GAME_STATE_UPDATE" for item in outgoing), 2)
        pass_window(engine)
        self.assertEqual(engine.state.phase, Phase.END_OF_COMBAT)
        self.assertIsNone(engine.state.permanent(attacker.card_id))
        self.assertTrue(all(engine.state.permanent(x.card_id) is None for x in blockers))

    def test_priority_timeout_is_treated_as_a_pass(self):
        engine = playing_engine()
        holder = engine.state.priority_holder

        outgoing = engine.expire_priority(engine.priority_deadline + 0.001)

        self.assertEqual(engine.state.priority_holder, engine.state.opponent_of(holder))
        self.assertEqual(sum(item.pdu["type"] == "PRIORITY_GRANT" for item in outgoing), 1)
        self.assertEqual(sum(item.pdu["type"] == "GAME_STATE_UPDATE" for item in outgoing), 2)

    def test_rejected_action_does_not_reset_the_existing_pass_sequence(self):
        engine = playing_engine()
        first = engine.state.priority_holder
        first_seat = engine.seat_for_player(first)
        engine.process(first_seat, {"type": "PRIORITY_PASS",
                                    "seq_num": engine.request_tokens[first_seat]})
        second = engine.state.priority_holder
        second_seat = engine.seat_for_player(second)
        token = engine.request_tokens[second_seat]

        engine.process(second_seat, {"type": "CAST_SPELL", "seq_num": token,
                                     "card_id": "not_in_hand", "targets": [],
                                     "mana_payment": {}})
        engine.process(second_seat, {"type": "PRIORITY_PASS", "seq_num": token})

        self.assertEqual(engine.state.phase, Phase.DRAW)


if __name__ == "__main__":
    unittest.main()
