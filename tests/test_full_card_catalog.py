import json
import unittest
from pathlib import Path

from server.game_engine import INSTANT_SORCERY_EFFECTS
from server.game_state import Phase, PermanentState
from tests.helpers import CATALOG, start_engine
from tests.test_card_effects import pass_twice, playing_engine


ROOT = Path(__file__).parents[1]


def cast(engine, player_id, card_id, lands=(), targets=(), choices=None):
    player = engine.state.players[player_id]
    if card_id not in player.hand and card_id not in player.madness_cards:
        player.hand.append(card_id)
    for land_id in lands:
        player.battlefield.append(PermanentState(
            land_id, player_id, player_id, summoning_sick=False))
    engine._grant_priority(player_id)
    card = engine.catalog.get(card_id)
    cost = dict(card.mana_cost)
    choices = dict(choices or {})
    if choices.get("suspend"):
        cost = {"R": 1}
    elif choices.get("madness"):
        cost = {"R": 1, "generic": 2}
    elif choices.get("kicked") and card.base_id == "goblin_bushwhacker":
        cost["R"] = cost.get("R", 0) + 1
        cost["generic"] = cost.get("generic", 0) + 1
    elif choices.get("kicked") and card.base_id == "vines_of_vastwood":
        cost["G"] = cost.get("G", 0) + 1
    payment = {"X" if color == "generic" else color: amount
               for color, amount in cost.items()}
    seat = engine.seat_for_player(player_id)
    return engine.process(seat, {
        "type": "CAST_SPELL", "seq_num": engine.request_tokens[seat],
        "card_id": card_id, "targets": list(targets),
        "mana_payment": payment, "choices": choices,
    })


def activate(engine, player_id, source_id, targets=(), mana=None, **payment):
    engine._grant_priority(player_id)
    seat = engine.seat_for_player(player_id)
    return engine.process(seat, {
        "type": "ACTIVATE_ABILITY", "seq_num": engine.request_tokens[seat],
        "source_id": source_id, "ability_index": 0,
        "targets": list(targets),
        "cost_payment": {"mana": dict(mana or {}), **payment},
    })


class FullCatalogCoverageTests(unittest.TestCase):
    def test_every_instant_and_sorcery_is_registered(self):
        spell_ids = {
            card.base_id for card in CATALOG.definitions.values()
            if card.card_type in {"Instant", "Sorcery"}
        }
        self.assertEqual(spell_ids, INSTANT_SORCERY_EFFECTS)

    def test_all_bundled_decks_are_unique_and_catalog_valid(self):
        expected = {"artifact.json", "black.json", "blue.json", "green.json",
                    "red.json", "white.json"}
        deck_paths = {path.name: path for path in (ROOT / "decks").glob("*.json")}
        self.assertTrue(expected.issubset(deck_paths))
        for name, path in deck_paths.items():
            with self.subTest(deck=name):
                cards = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(len(cards), len(set(cards)))
                CATALOG.validate_deck(cards)

    def test_rift_bolt_suspend_casts_without_an_initial_target(self):
        engine = playing_engine()
        caster = engine.state.active_player
        opponent = engine.state.opponent_of(caster)
        cast(engine, caster, "rift_bolt_001", ["mountain_020"], choices={"suspend": True})
        self.assertIn("rift_bolt_001", engine.state.players[caster].exile)
        engine.state.phase = Phase.UNTAP
        outgoing = engine._enter_priority_phase(Phase.UPKEEP)
        self.assertTrue(any(item.pdu["type"] == "STACK_PUSH" for item in outgoing))
        pass_twice(engine)
        self.assertEqual(engine.state.players[opponent].life, 17)

    def test_kicker_prowess_and_madness_paths(self):
        engine = playing_engine()
        caster = engine.state.active_player
        player = engine.state.players[caster]
        swiftspear = PermanentState("monastery_swiftspear_001", caster, caster,
                                    summoning_sick=False)
        bear = PermanentState("grizzly_bears_001", caster, caster,
                              summoning_sick=False)
        player.battlefield.extend([swiftspear, bear])
        cast(engine, caster, "vines_of_vastwood_001",
             ["forest_019", "forest_020"], [bear.card_id], {"kicked": True})
        self.assertEqual((swiftspear.power_modifier, swiftspear.toughness_modifier), (1, 1))
        pass_twice(engine)
        self.assertEqual((bear.power_modifier, bear.toughness_modifier), (4, 4))

        player.hand.append("reckless_wurm_001")
        player.hand.remove("reckless_wurm_001")
        engine._discard_card(player, "reckless_wurm_001")
        snapshot = engine.state.visible_to(caster, engine.catalog)
        self.assertEqual(snapshot["madness"], ["reckless_wurm_001"])
        cast(engine, caster, "reckless_wurm_001",
             ["mountain_018", "mountain_019", "mountain_020"],
             choices={"madness": True})
        pass_twice(engine)
        self.assertIsNotNone(engine.state.permanent("reckless_wurm_001"))

    def test_white_exile_uses_the_affected_controller(self):
        engine = playing_engine()
        caster = engine.state.active_player
        opponent = engine.state.opponent_of(caster)
        controlled = PermanentState("grizzly_bears_001", caster, opponent,
                                    summoning_sick=False)
        engine.state.players[opponent].battlefield.append(controlled)
        cast(engine, caster, "swords_to_plowshares_001", ["plains_020"],
             [controlled.card_id])
        pass_twice(engine)
        self.assertEqual(engine.state.players[opponent].life, 22)
        self.assertIn(controlled.card_id, engine.state.players[caster].exile)

    def test_healing_salve_and_skullcrack_prevention(self):
        engine = playing_engine()
        caster = engine.state.active_player
        opponent = engine.state.opponent_of(caster)
        cast(engine, caster, "healing_salve_001", ["plains_020"], [opponent],
             {"mode": "prevent"})
        pass_twice(engine)
        self.assertEqual(engine.state.players[opponent].damage_prevention, 3)
        cast(engine, caster, "skullcrack_001", ["mountain_019", "mountain_020"],
             [opponent])
        pass_twice(engine)
        self.assertEqual(engine.state.players[opponent].life, 17)

    def test_activated_mana_loot_mill_damage_protection_and_regeneration(self):
        engine = playing_engine()
        player_id = engine.state.active_player
        opponent = engine.state.opponent_of(player_id)
        player = engine.state.players[player_id]

        ring = PermanentState("sol_ring_001", player_id, player_id, summoning_sick=False)
        player.battlefield.append(ring)
        activate(engine, player_id, ring.card_id)
        self.assertEqual(player.mana_pool, {"C": 2})

        looter = PermanentState("merfolk_looter_001", player_id, player_id,
                                summoning_sick=False)
        player.battlefield.append(looter)
        player.library.append("island_020")
        player.hand.append("reckless_wurm_002")
        activate(engine, player_id, looter.card_id, discard_id="reckless_wurm_002")
        pass_twice(engine)
        self.assertIn("reckless_wurm_002", player.madness_cards)

        mill = PermanentState("millstone_001", player_id, player_id, summoning_sick=False)
        player.battlefield.append(mill)
        player.mana_pool = {"C": 2}
        before = len(engine.state.players[opponent].graveyard)
        activate(engine, player_id, mill.card_id, [opponent], {"X": 2})
        pass_twice(engine)
        self.assertEqual(len(engine.state.players[opponent].graveyard), before + 2)

        troll = PermanentState("troll_ascetic_001", player_id, player_id,
                               summoning_sick=True)
        player.battlefield.append(troll)
        player.mana_pool = {"G": 1, "C": 1}
        activate(engine, player_id, troll.card_id, mana={"G": 1, "X": 1})
        pass_twice(engine)
        self.assertEqual(troll.regeneration_shields, 1)
        self.assertFalse(engine._destroy(troll))
        self.assertIsNotNone(engine.state.permanent(troll.card_id))

    def test_phantasmal_bear_sacrifices_when_targeted_by_an_ability(self):
        engine = playing_engine()
        player_id = engine.state.active_player
        opponent = engine.state.opponent_of(player_id)
        source = PermanentState("prodigal_sorcerer_001", player_id, player_id,
                                summoning_sick=False)
        bear = PermanentState("phantasmal_bear_001", opponent, opponent,
                              summoning_sick=False)
        engine.state.players[player_id].battlefield.append(source)
        engine.state.players[opponent].battlefield.append(bear)
        outgoing = activate(engine, player_id, source.card_id, [bear.card_id])
        pushes = [item for item in outgoing if item.pdu["type"] == "STACK_PUSH"]
        self.assertEqual(len(pushes), 2)
        pass_twice(engine)
        self.assertIsNone(engine.state.permanent(bear.card_id))

    def test_mother_royal_assassin_rod_and_gravedigger(self):
        engine = playing_engine()
        player_id = engine.state.active_player
        opponent = engine.state.opponent_of(player_id)
        player = engine.state.players[player_id]
        opposing = engine.state.players[opponent]

        mother = PermanentState("mother_of_runes_001", player_id, player_id,
                                summoning_sick=False)
        protected = PermanentState("grizzly_bears_001", player_id, player_id,
                                   summoning_sick=False)
        aura = PermanentState("pacifism_001", opponent, opponent,
                              attached_to=protected.card_id)
        player.battlefield.extend([mother, protected])
        opposing.battlefield.append(aura)
        activate(engine, player_id, mother.card_id, [protected.card_id], color="W")
        pass_twice(engine)
        self.assertIn("W", protected.protection_colors)
        self.assertIsNone(engine.state.permanent(aura.card_id))

        assassin = PermanentState("royal_assassin_001", player_id, player_id,
                                  summoning_sick=False)
        victim = PermanentState("savannah_lions_001", opponent, opponent,
                                tapped=True, summoning_sick=False)
        player.battlefield.append(assassin)
        opposing.battlefield.append(victim)
        activate(engine, player_id, assassin.card_id, [victim.card_id])
        pass_twice(engine)
        self.assertIsNone(engine.state.permanent(victim.card_id))

        rod = PermanentState("rod_of_ruin_001", player_id, player_id,
                             summoning_sick=False)
        player.battlefield.append(rod)
        player.mana_pool = {"C": 3}
        activate(engine, player_id, rod.card_id, [opponent], {"X": 3})
        pass_twice(engine)
        self.assertEqual(opposing.life, 19)

        player.graveyard.append("phantasmal_bear_002")
        cast(engine, player_id, "gravedigger_001",
             [f"swamp_{index:03d}" for index in range(17, 21)],
             ["phantasmal_bear_002"])
        pass_twice(engine)
        self.assertIn("phantasmal_bear_002", player.hand)

    def test_rampant_growth_naturalize_path_and_pacifism_zone_rules(self):
        engine = playing_engine()
        player_id = engine.state.active_player
        opponent = engine.state.opponent_of(player_id)
        player = engine.state.players[player_id]
        opposing = engine.state.players[opponent]

        player.library.append("forest_020")
        battlefield_before = len(player.battlefield)
        cast(engine, player_id, "rampant_growth_001",
             ["forest_018", "forest_019"])
        pass_twice(engine)
        self.assertEqual(len(player.battlefield), battlefield_before + 3)
        self.assertTrue(any(
            permanent.tapped and engine.catalog.get(permanent.card_id).card_type == "Land"
            for permanent in player.battlefield
        ))

        artifact = PermanentState("millstone_002", opponent, opponent,
                                  summoning_sick=False)
        opposing.battlefield.append(artifact)
        cast(engine, player_id, "naturalize_001",
             ["forest_016", "forest_017"], [artifact.card_id])
        pass_twice(engine)
        self.assertIsNone(engine.state.permanent(artifact.card_id))

        creature = PermanentState("savannah_lions_002", opponent, opponent,
                                  summoning_sick=False)
        opposing.battlefield.append(creature)
        opposing.library.append("island_020")
        before = len(opposing.battlefield)
        cast(engine, player_id, "path_to_exile_001", ["plains_020"],
             [creature.card_id], {"search": True})
        pass_twice(engine)
        self.assertIn(creature.card_id, opposing.exile)
        self.assertEqual(len(opposing.battlefield), before)

        replacement = PermanentState("savannah_lions_003", opponent, opponent,
                                     summoning_sick=False)
        opposing.battlefield.append(replacement)
        cast(engine, player_id, "pacifism_001", ["plains_018", "plains_019"],
             [replacement.card_id])
        pass_twice(engine)
        self.assertTrue(engine._is_pacified(replacement.card_id))

    def test_trample_assigns_only_lethal_damage_to_the_final_blocker(self):
        engine = playing_engine()
        attacker_id = engine.state.active_player
        defender_id = engine.state.opponent_of(attacker_id)
        attacker = PermanentState("reckless_wurm_003", attacker_id, attacker_id,
                                  summoning_sick=False)
        blocker = PermanentState("ornithopter_003", defender_id, defender_id,
                                 summoning_sick=False)
        engine.state.players[attacker_id].battlefield = [attacker]
        engine.state.players[defender_id].battlefield = [blocker]
        engine.state.combat.attackers = [attacker.card_id]
        engine.state.combat.blockers = {attacker.card_id: [blocker.card_id]}
        engine.resolve_combat_damage(first_strike=False)
        self.assertEqual(engine.state.players[defender_id].life, 18)
        self.assertIsNone(engine.state.permanent(blocker.card_id))

    def test_zero_toughness_bypasses_a_regeneration_shield(self):
        engine = playing_engine()
        player_id = engine.state.active_player
        creature = PermanentState("grizzly_bears_001", player_id, player_id,
                                  toughness_modifier=-2, regeneration_shields=1)
        engine.state.players[player_id].battlefield.append(creature)
        self.assertEqual(engine._state_based_actions(), [creature.card_id])
        self.assertIsNone(engine.state.permanent(creature.card_id))


if __name__ == "__main__":
    unittest.main()
