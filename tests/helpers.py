import random
from pathlib import Path

from common.cards import CardCatalog
from server.game_engine import GameEngine

ROOT = Path(__file__).parents[1]
CATALOG = CardCatalog.from_json(ROOT / "cards.json")
RED_DECK = [f"mountain_{i:03d}" for i in range(1, 9)] + [
    "lightning_bolt_001", "goblin_guide_001", "wall_of_stone_001", "gray_merchant_001"]
BLUE_DECK = [f"island_{i:03d}" for i in range(1, 9)] + [
    "counterspell_001", "unsummon_001", "giant_growth_001", "ornithopter_001"]


def ready(player_id, deck, seq=1):
    return {"type": "PLAYER_READY", "seq_num": seq,
            "player_id": player_id, "deck_list": list(deck)}


def make_engine(seed=3):
    return GameEngine(CATALOG, random.Random(seed), priority_timeout_ms=1000)


def start_engine():
    engine = make_engine()
    engine.process("seat_1", ready("player_1", RED_DECK))
    engine.process("seat_2", ready("player_2", BLUE_DECK))
    return engine
