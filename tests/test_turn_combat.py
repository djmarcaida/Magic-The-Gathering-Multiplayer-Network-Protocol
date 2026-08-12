import unittest

from server.game_state import Lifecycle, PHASE_ORDER, Phase, PermanentState
from tests.helpers import start_engine


def playing_engine():
    engine = start_engine()
    for seat in ("seat_1", "seat_2"):
        engine.process(seat, {"type": "MULLIGAN_CHOICE",
                              "seq_num": engine.request_tokens[seat],
                              "keep": True, "cards_to_bottom": []})
    return engine


class TurnAndCombatTests(unittest.TestCase):
    def test_phase_order_matches_required_cycle(self):
        engine = playing_engine()
        self.assertEqual(PHASE_ORDER, tuple(Phase))
        active = engine.state.active_player
        engine.state.phase = Phase.CLEANUP
        engine.advance_step()
        self.assertEqual((engine.state.phase, engine.state.turn), (Phase.UPKEEP, 2))
        self.assertNotEqual(engine.state.active_player, active)

    def test_play_land_only_in_active_players_main_phase_and_once_per_turn(self):
        engine = playing_engine()
        player_id = engine.state.active_player
        seat = engine.seat_for_player(player_id)
        player = engine.state.players[player_id]
        land = next((x for x in player.hand if x.startswith(("mountain_", "island_"))), None)
        if land is None:
            land = "mountain_020"
            player.hand.append(land)
        engine.state.phase = Phase.PRECOMBAT_MAIN
        result = engine.process(seat, {"type": "PLAY_LAND",
                                       "seq_num": engine.request_tokens[seat], "card_id": land})
        self.assertEqual(player.battlefield[-1].card_id, land)
        second = "mountain_019"
        player.hand.append(second)
        error = engine.process(seat, {"type": "PLAY_LAND",
                                      "seq_num": engine.request_tokens[seat], "card_id": second})
        self.assertEqual(error[0].pdu["code"], "ILLEGAL_ACTION")

    def test_untap_clears_taps_and_summoning_sickness(self):
        engine = playing_engine()
        player = engine.state.players[engine.state.opponent_of(engine.state.active_player)]
        player.battlefield.append(PermanentState("goblin_guide_001", player.player_id,
                                                  player.player_id, tapped=True,
                                                  summoning_sick=True))
        engine.state.phase = Phase.CLEANUP
        engine.advance_step()
        permanent = player.battlefield[-1]
        self.assertFalse(permanent.tapped)
        self.assertFalse(permanent.summoning_sick)

    def test_attack_block_and_simultaneous_combat_damage(self):
        engine = playing_engine()
        attacker_id = engine.state.active_player
        defender_id = engine.state.opponent_of(attacker_id)
        attacker = PermanentState("goblin_guide_001", attacker_id, attacker_id,
                                  summoning_sick=False)
        blocker = PermanentState("phantasmal_bear_001", defender_id, defender_id,
                                 summoning_sick=False)
        engine.state.players[attacker_id].battlefield = [attacker]
        engine.state.players[defender_id].battlefield = [blocker]
        engine.state.combat.attackers = [attacker.card_id]
        engine.state.combat.blockers = {attacker.card_id: [blocker.card_id]}
        engine.state.phase = Phase.COMBAT_DAMAGE
        outgoing = engine.resolve_combat_damage(first_strike=False)
        self.assertEqual(engine.state.players[attacker_id].battlefield, [])
        self.assertEqual(engine.state.players[defender_id].battlefield, [])
        result = next(x.pdu for x in outgoing if x.pdu["type"] == "COMBAT_DAMAGE_RESULT")
        self.assertEqual(len(result["creatures_died"]), 2)

    def test_ground_creature_cannot_block_flying_attacker(self):
        engine = playing_engine()
        attacker_id = engine.state.active_player
        defender_id = engine.state.opponent_of(attacker_id)
        attacker = PermanentState("ornithopter_001", attacker_id, attacker_id,
                                  summoning_sick=False)
        blocker = PermanentState("wall_of_stone_001", defender_id, defender_id,
                                 summoning_sick=False)
        engine.state.players[attacker_id].battlefield = [attacker]
        engine.state.players[defender_id].battlefield = [blocker]
        engine.state.combat.attackers = [attacker.card_id]
        engine.state.phase = Phase.DECLARE_BLOCKERS
        engine._grant_priority(defender_id)
        seat = engine.seat_for_player(defender_id)

        outgoing = engine.process(seat, {
            "type": "DECLARE_BLOCKERS", "seq_num": engine.request_tokens[seat],
            "blockers": [{"creature_id": blocker.card_id,
                          "blocking_id": attacker.card_id}],
        })

        self.assertEqual(outgoing[0].pdu["code"], "ILLEGAL_ACTION")
        self.assertEqual(engine.state.combat.blockers, {})

    def test_protection_from_color_prevents_blocking(self):
        engine = playing_engine()
        attacker_id = engine.state.active_player
        defender_id = engine.state.opponent_of(attacker_id)
        attacker = PermanentState("black_knight_001", attacker_id, attacker_id,
                                  summoning_sick=False)
        blocker = PermanentState("savannah_lions_001", defender_id, defender_id,
                                 summoning_sick=False)
        engine.state.players[attacker_id].battlefield = [attacker]
        engine.state.players[defender_id].battlefield = [blocker]
        engine.state.combat.attackers = [attacker.card_id]
        engine.state.phase = Phase.DECLARE_BLOCKERS
        engine._grant_priority(defender_id)
        seat = engine.seat_for_player(defender_id)

        outgoing = engine.process(seat, {
            "type": "DECLARE_BLOCKERS", "seq_num": engine.request_tokens[seat],
            "blockers": [{"creature_id": blocker.card_id,
                          "blocking_id": attacker.card_id}],
        })

        self.assertEqual(outgoing[0].pdu["code"], "ILLEGAL_ACTION")
        self.assertEqual(engine.state.combat.blockers, {})


if __name__ == "__main__":
    unittest.main()
