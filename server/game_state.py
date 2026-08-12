"""Authoritative, serializable game state with private-zone filtering."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from random import Random
from typing import Any


class Lifecycle(str, Enum):
    """Broad phases of a game session from lobby through completion."""
    LOBBY = "LOBBY"
    MULLIGAN = "MULLIGAN"
    PLAYING = "PLAYING"
    GAME_OVER = "GAME_OVER"


class Phase(str, Enum):
    """Granular steps and phases within a single turn."""
    UNTAP = "UNTAP"
    UPKEEP = "UPKEEP"
    DRAW = "DRAW"
    PRECOMBAT_MAIN = "PRECOMBAT_MAIN"
    BEGIN_COMBAT = "BEGIN_COMBAT"
    DECLARE_ATTACKERS = "DECLARE_ATTACKERS"
    DECLARE_BLOCKERS = "DECLARE_BLOCKERS"
    ASSIGN_DAMAGE_ORDER = "ASSIGN_DAMAGE_ORDER"
    FIRST_STRIKE_DAMAGE = "FIRST_STRIKE_DAMAGE"
    COMBAT_DAMAGE = "COMBAT_DAMAGE"
    END_OF_COMBAT = "END_OF_COMBAT"
    POSTCOMBAT_MAIN = "POSTCOMBAT_MAIN"
    END_STEP = "END_STEP"
    CLEANUP = "CLEANUP"


PHASE_ORDER = tuple(Phase)


@dataclass
class PermanentState:
    """Represents a single card instance currently on the battlefield."""
    card_id: str
    owner: str
    controller: str
    tapped: bool = False
    summoning_sick: bool = True
    damage: int = 0
    power_modifier: int = 0
    toughness_modifier: int = 0
    attached_to: str | None = None
    temporary_keywords: list[str] = field(default_factory=list)
    protection_colors: list[str] = field(default_factory=list)
    regeneration_shields: int = 0
    damage_prevention: int = 0
    cant_regenerate: bool = False
    opponent_hexproof: bool = False


@dataclass
class StackItem:
    """Represents a spell, triggered ability, or activated ability on the stack."""
    stack_item_id: str
    item_type: str
    source: str
    controller: str
    targets: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CombatState:
    """Tracks current combat participants and damage assignment orders."""
    attackers: list[str] = field(default_factory=list)
    blockers: dict[str, list[str]] = field(default_factory=dict)
    damage_order: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class PlayerState:
    """Authoritative tracker for all private and public zones of a specific player."""
    player_id: str
    life: int = 20
    library: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)
    battlefield: list[PermanentState] = field(default_factory=list)
    graveyard: list[str] = field(default_factory=list)
    exile: list[str] = field(default_factory=list)
    mana_pool: dict[str, int] = field(default_factory=dict)
    suspended: dict[str, int] = field(default_factory=dict)
    madness_cards: list[str] = field(default_factory=list)
    damage_prevention: int = 0
    land_played: bool = False
    mulligans: int = 0
    kept: bool = False


@dataclass
class GameState:
    """
    The single source of truth for the entire match.

    Maintains all player states, turn phases, combat, and the stack.
    Responsible for generating the filtered 'visible' state payload for clients.
    """
    players: dict[str, PlayerState]
    seats: dict[str, str]
    first_player: str
    active_player: str
    lifecycle: Lifecycle = Lifecycle.MULLIGAN
    phase: Phase = Phase.UNTAP
    turn: int = 1
    priority_holder: str | None = None
    priority_token: int | None = None
    stack: list[StackItem] = field(default_factory=list)
    combat: CombatState = field(default_factory=CombatState)
    life_gain_locked: bool = False
    damage_prevention_locked: bool = False

    @classmethod
    def new(cls, players: tuple[str, str], decks: dict[str, list[str]],
            first_player: str, rng: Random) -> "GameState":
        states: dict[str, PlayerState] = {}
        for player_id in players:
            library = list(decks[player_id])
            rng.shuffle(library)
            hand = [library.pop() for _ in range(min(7, len(library)))]
            states[player_id] = PlayerState(player_id, library=library, hand=hand)
        return cls(states, {}, first_player, first_player)

    def opponent_of(self, player_id: str) -> str:
        return next(pid for pid in self.players if pid != player_id)

    def permanent(self, card_id: str) -> PermanentState | None:
        for player in self.players.values():
            for permanent in player.battlefield:
                if permanent.card_id == card_id:
                    return permanent
        return None

    def visible_to(self, player_id: str, catalog: Any) -> dict[str, object]:
        def public_permanent(permanent: PermanentState) -> dict[str, object]:
            card = catalog.get(permanent.card_id)
            d: dict[str, object] = {
                "id": permanent.card_id,
                "tapped": permanent.tapped,
                "attached_to": permanent.attached_to,
                "temporary_keywords": list(permanent.temporary_keywords),
                "protection_colors": list(permanent.protection_colors),
                "regeneration_shields": permanent.regeneration_shields,
            }
            if "Creature" in card.card_type:
                d["damage"] = permanent.damage
                d["power"] = (card.power or 0) + permanent.power_modifier
                d["toughness"] = (card.toughness or 0) + permanent.toughness_modifier
                d["summoning_sick"] = permanent.summoning_sick
            return d

        return {
            "lifecycle": self.lifecycle.value,
            "phase": self.phase.value,
            "turn": self.turn,
            "first_player": self.first_player,
            "active_player": self.active_player,
            "priority_holder": self.priority_holder,
            "priority_token": self.priority_token if self.priority_holder == player_id else None,
            "life_totals": {pid: p.life for pid, p in self.players.items()},
            "mana_pools": {pid: dict(p.mana_pool) for pid, p in self.players.items()},
            "suspended": {pid: dict(p.suspended) for pid, p in self.players.items()},
            "madness": list(self.players[player_id].madness_cards),
            "hand": list(self.players[player_id].hand),
            "hand_counts": {pid: len(p.hand) for pid, p in self.players.items()},
            "library_counts": {pid: len(p.library) for pid, p in self.players.items()},
            "land_played_this_turn": self.players[self.active_player].land_played,
            "battlefield": {pid: [public_permanent(x) for x in p.battlefield]
                            for pid, p in self.players.items()},
            "graveyard": {pid: list(p.graveyard) for pid, p in self.players.items()},
            "exile": {pid: list(p.exile) for pid, p in self.players.items()},
            "stack": [asdict(item) for item in self.stack],
            "combat": asdict(self.combat),
        }
