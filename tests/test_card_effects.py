import unittest

from server.game_state import Phase, PermanentState
from tests.helpers import start_engine


def playing_engine():
    engine = start_engine()
    for seat in ("seat_1", "seat_2"):
        engine.process(seat, {"type": "MULLIGAN_CHOICE", "seq_num": engine.request_tokens[seat],
                              "keep": True, "cards_to_bottom": []})
    engine.state.phase = Phase.PRECOMBAT_MAIN
    return engine


def give_cast(engine, player_id, card_id, lands, targets):
    player = engine.state.players[player_id]
    player.hand.append(card_id)
    color = {"mountain": "R", "island": "U", "forest": "G", "swamp": "B", "plains": "W"}
    for land_id in lands:
        player.battlefield.append(PermanentState(land_id, player_id, player_id,
                                                  summoning_sick=False))
    seat = engine.seat_for_player(player_id)
    engine._grant_priority(player_id)
    cost = dict(engine.catalog.get(card_id).mana_cost)
    payment = {"X" if key == "generic" else key: amount for key, amount in cost.items()}
    return engine.process(seat, {"type": "CAST_SPELL", "seq_num": engine.request_tokens[seat],
                                 "card_id": card_id, "targets": targets,
                                 "mana_payment": payment})


def pass_twice(engine):
    first = engine.state.priority_holder
    first_seat = engine.seat_for_player(first)
    engine.process(first_seat, {"type": "PRIORITY_PASS",
                                "seq_num": engine.request_tokens[first_seat]})
    second = engine.state.priority_holder
    second_seat = engine.seat_for_player(second)
    return engine.process(second_seat, {"type": "PRIORITY_PASS",
                                        "seq_num": engine.request_tokens[second_seat]})


class RequiredCardEffectTests(unittest.TestCase):
    def test_lightning_bolt_deals_three_to_player(self):
        engine = playing_engine()
        caster = engine.state.active_player
        target = engine.state.opponent_of(caster)
        give_cast(engine, caster, "lightning_bolt_001", ["mountain_020"], [target])
        pass_twice(engine)
        self.assertEqual(engine.state.players[target].life, 17)

    def test_counterspell_removes_target_spell_from_stack(self):
        engine = playing_engine()
        caster = engine.state.active_player
        responder = engine.state.opponent_of(caster)
        give_cast(engine, caster, "lightning_bolt_001", ["mountain_020"], [responder])
        bolt_stack_id = engine.state.stack[-1].stack_item_id
        caster_seat = engine.seat_for_player(caster)
        engine.process(caster_seat, {"type": "PRIORITY_PASS", "seq_num": engine.request_tokens[caster_seat]})
        give_cast(engine, responder, "counterspell_001", ["island_019", "island_020"], [bolt_stack_id])
        pass_twice(engine)
        self.assertEqual(engine.state.players[responder].life, 20)
        self.assertEqual(engine.state.stack, [])

    def test_unsummon_returns_creature_to_owners_hand(self):
        engine = playing_engine()
        caster = engine.state.active_player
        owner = engine.state.opponent_of(caster)
        creature = PermanentState("goblin_guide_001", owner, owner, summoning_sick=False)
        engine.state.players[owner].battlefield.append(creature)
        give_cast(engine, caster, "unsummon_001", ["island_020"], [creature.card_id])
        pass_twice(engine)
        self.assertIn(creature.card_id, engine.state.players[owner].hand)
        self.assertIsNone(engine.state.permanent(creature.card_id))

    def test_giant_growth_expires_at_cleanup(self):
        engine = playing_engine()
        caster = engine.state.active_player
        creature = PermanentState("grizzly_bears_001", caster, caster, summoning_sick=False)
        engine.state.players[caster].battlefield.append(creature)
        give_cast(engine, caster, "giant_growth_001", ["forest_020"], [creature.card_id])
        pass_twice(engine)
        self.assertEqual((creature.power_modifier, creature.toughness_modifier), (3, 3))
        engine.state.phase = Phase.END_STEP
        engine.advance_step()
        self.assertEqual((creature.power_modifier, creature.toughness_modifier), (0, 0))

    def test_gray_merchant_uses_black_mana_symbols_for_devotion(self):
        engine = playing_engine()
        caster = engine.state.active_player
        opponent = engine.state.opponent_of(caster)
        existing = PermanentState("black_knight_001", caster, caster, summoning_sick=False)
        engine.state.players[caster].battlefield.append(existing)
        lands = [f"swamp_{i:03d}" for i in range(16, 21)]
        give_cast(engine, caster, "gray_merchant_001", lands, [])
        first_resolution = pass_twice(engine)
        self.assertEqual(engine.state.stack[-1].item_type, "TRIGGER")
        self.assertTrue(any(x.pdu["type"] == "STACK_PUSH" for x in first_resolution))
        pass_twice(engine)
        self.assertEqual(engine.state.players[opponent].life, 16)
        self.assertEqual(engine.state.players[caster].life, 24)

    def test_life_zero_emits_game_over_and_resets_to_lobby(self):
        engine = playing_engine()
        caster = engine.state.active_player
        target = engine.state.opponent_of(caster)
        engine.state.players[target].life = 3
        give_cast(engine, caster, "lightning_bolt_001", ["mountain_020"], [target])
        outgoing = pass_twice(engine)
        game_over = next(x.pdu for x in outgoing if x.pdu["type"] == "GAME_OVER")
        self.assertEqual((game_over["winner_id"], game_over["reason"]),
                         (caster, "LIFE_ZERO"))
        self.assertIsNone(engine.state)


if __name__ == "__main__":
    unittest.main()
