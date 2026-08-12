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

    def test_lightning_bolt_rejects_a_land_target(self):
        engine = playing_engine()
        caster = engine.state.active_player
        opponent = engine.state.opponent_of(caster)
        land = PermanentState("forest_001", opponent, opponent,
                              summoning_sick=False)
        engine.state.players[opponent].battlefield.append(land)

        outgoing = give_cast(engine, caster, "lightning_bolt_001",
                             ["mountain_020"], [land.card_id])

        error = next(item.pdu for item in outgoing if item.pdu["type"] == "ERROR")
        self.assertEqual(error["code"], "ILLEGAL_TARGET")
        self.assertIn("lightning_bolt_001", engine.state.players[caster].hand)

    def test_shock_deals_two_and_lava_spike_only_targets_players(self):
        engine = playing_engine()
        caster = engine.state.active_player
        target = engine.state.opponent_of(caster)
        give_cast(engine, caster, "shock_001", ["mountain_020"], [target])
        pass_twice(engine)
        self.assertEqual(engine.state.players[target].life, 18)

        creature = PermanentState("ornithopter_001", target, target, summoning_sick=False)
        engine.state.players[target].battlefield.append(creature)
        outgoing = give_cast(engine, caster, "lava_spike_001",
                             ["mountain_019"], [creature.card_id])
        self.assertEqual(outgoing[0].pdu["code"], "ILLEGAL_TARGET")
        self.assertEqual(creature.damage, 0)

    def test_dark_ritual_pool_pays_for_doom_blade_and_empties_on_transition(self):
        engine = playing_engine()
        caster = engine.state.active_player
        target_player = engine.state.opponent_of(caster)
        target = PermanentState("wall_of_stone_001", target_player, target_player,
                                summoning_sick=False)
        engine.state.players[target_player].battlefield.append(target)

        give_cast(engine, caster, "dark_ritual_001", ["swamp_020"], [])
        pass_twice(engine)
        self.assertEqual(engine.state.players[caster].mana_pool, {"B": 3})

        give_cast(engine, caster, "doom_blade_001", [], [target.card_id])
        pass_twice(engine)
        self.assertIsNone(engine.state.permanent(target.card_id))
        self.assertIn(target.card_id, engine.state.players[target_player].graveyard)
        self.assertEqual(engine.state.players[caster].mana_pool, {"B": 1})

        engine._transition(engine.state.phase, Phase.BEGIN_COMBAT)
        self.assertEqual(engine.state.players[caster].mana_pool, {})

    def test_doom_blade_and_terror_enforce_black_and_artifact_restrictions(self):
        engine = playing_engine()
        caster = engine.state.active_player
        opponent = engine.state.opponent_of(caster)
        black = PermanentState("black_knight_001", opponent, opponent,
                               summoning_sick=False)
        artifact = PermanentState("ornithopter_001", opponent, opponent,
                                  summoning_sick=False)
        engine.state.players[opponent].battlefield.extend([black, artifact])

        doom = give_cast(engine, caster, "doom_blade_001",
                         ["swamp_019", "swamp_020"], [black.card_id])
        self.assertEqual(doom[0].pdu["code"], "ILLEGAL_TARGET")
        terror = give_cast(engine, caster, "terror_001",
                           ["swamp_017", "swamp_018"], [artifact.card_id])
        self.assertEqual(terror[0].pdu["code"], "ILLEGAL_TARGET")

    def test_mind_rot_discards_two_and_raise_dead_recovers_a_creature(self):
        engine = playing_engine()
        caster = engine.state.active_player
        opponent = engine.state.opponent_of(caster)
        opponent_state = engine.state.players[opponent]
        opponent_state.hand = ["mountain_001", "goblin_guide_001", "shock_001"]

        give_cast(engine, caster, "mind_rot_001",
                  ["swamp_018", "swamp_019", "swamp_020"], [opponent])
        pass_twice(engine)
        self.assertEqual(opponent_state.hand, ["mountain_001"])
        self.assertEqual(opponent_state.graveyard[-2:],
                         ["goblin_guide_001", "shock_001"])

        caster_state = engine.state.players[caster]
        caster_state.graveyard.append("black_knight_002")
        give_cast(engine, caster, "raise_dead_001", ["swamp_017"],
                  ["black_knight_002"])
        pass_twice(engine)
        self.assertIn("black_knight_002", caster_state.hand)
        self.assertNotIn("black_knight_002", caster_state.graveyard)

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
        self.assertEqual(engine.state.stack[-1].item_type, "TRIGGER_ABILITY")
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
