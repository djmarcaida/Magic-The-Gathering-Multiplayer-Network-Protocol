"""Pure GUI projection helpers and Tk-main-thread event handoff."""

from __future__ import annotations

import json
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PHASE_LABELS = {
    "UNTAP": "Untap",
    "UPKEEP": "Upkeep",
    "DRAW": "Draw",
    "PRECOMBAT_MAIN": "Pre-combat main",
    "BEGIN_COMBAT": "Begin combat",
    "DECLARE_ATTACKERS": "Declare attackers",
    "DECLARE_BLOCKERS": "Declare blockers",
    "ASSIGN_DAMAGE_ORDER": "Assign damage order",
    "FIRST_STRIKE_DAMAGE": "First-strike damage",
    "COMBAT_DAMAGE": "Combat damage",
    "END_OF_COMBAT": "End of combat",
    "POSTCOMBAT_MAIN": "Post-combat main",
    "END_STEP": "End step",
    "CLEANUP": "Cleanup",
}

SUPPORTED_SPELL_EFFECTS = {
    "lightning_bolt", "shock", "lava_spike", "flame_slash", "searing_spear",
    "skullcrack", "rift_bolt", "incinerate", "counterspell", "cancel",
    "unsummon", "ponder", "negate", "mana_leak", "giant_growth",
    "rampant_growth", "naturalize", "vines_of_vastwood", "swords_to_plowshares",
    "path_to_exile", "healing_salve", "dark_ritual", "terror", "doom_blade",
    "raise_dead", "mind_rot",
}
TARGETED_SPELL_EFFECTS = {
    "lightning_bolt", "shock", "lava_spike", "flame_slash", "searing_spear",
    "skullcrack", "rift_bolt", "incinerate", "counterspell", "cancel", "negate",
    "mana_leak", "unsummon", "giant_growth", "vines_of_vastwood", "naturalize",
    "swords_to_plowshares", "path_to_exile", "healing_salve", "doom_blade",
    "terror", "mind_rot", "raise_dead", "pacifism", "gravedigger",
}

ACTIVATED_ABILITY_CARDS = {
    "sol_ring", "llanowar_elves", "elvish_mystic", "merfolk_looter",
    "prodigal_sorcerer", "troll_ascetic", "mother_of_runes", "royal_assassin",
    "millstone", "rod_of_ruin",
}

CARD_BORDER_COLORS = {
    "W": "#F3DF9B",
    "U": "#63A8D5",
    "B": "#997AAF",
    "R": "#D76A5B",
    "G": "#63AA73",
}
COLORLESS_CARD_BORDER = "#AFB5B1"
MULTICOLOR_CARD_BORDER = "#D5AD49"
MANA_SOURCE_OUTPUTS = {
    "mountain": ("R", 1),
    "island": ("U", 1),
    "forest": ("G", 1),
    "swamp": ("B", 1),
    "plains": ("W", 1),
    "sol_ring": ("C", 2),
    "llanowar_elves": ("G", 1),
    "elvish_mystic": ("G", 1),
}


def base_card_id(instance_id: str) -> str:
    """Return the catalog ID portion of a `<base>_<copy>` instance ID."""
    base, separator, copy = instance_id.rpartition("_")
    return base if separator and len(copy) == 3 and copy.isdigit() else instance_id


@dataclass(frozen=True)
class CardDefinition:
    base_id: str
    name: str
    card_type: str
    subtype: str
    colors: tuple[str, ...]
    mana_cost: dict[str, int]
    power: int | None
    toughness: int | None
    keywords: tuple[str, ...]
    effect: str


class CardCatalog:
    def __init__(self, definitions: dict[str, CardDefinition]):
        self._definitions = definitions

    @classmethod
    def from_path(cls, path: str | Path) -> "CardCatalog":
        records = json.loads(Path(path).read_text(encoding="utf-8"))
        definitions = {
            item["base_id"]: CardDefinition(
                base_id=item["base_id"],
                name=item["name"],
                card_type=item["card_type"],
                subtype=item.get("subtype", ""),
                colors=tuple(item.get("colors", ())),
                mana_cost=dict(item.get("mana_cost", {})),
                power=item.get("power"),
                toughness=item.get("toughness"),
                keywords=tuple(item.get("keywords", ())),
                effect=item.get("effect", ""),
            )
            for item in records
        }
        return cls(definitions)

    def card(self, instance_id: str) -> CardDefinition:
        return self._definitions[base_card_id(instance_id)]


@dataclass(frozen=True)
class CardView:
    instance_id: str
    base_id: str
    name: str
    card_type: str
    subtype: str
    colors: tuple[str, ...]
    mana_cost: dict[str, int]
    power: int | None
    toughness: int | None
    keywords: tuple[str, ...]
    effect: str
    tapped: bool = False
    summoning_sick: bool = False
    damage: int = 0
    power_modifier: int = 0
    toughness_modifier: int = 0
    owner: str = ""
    controller: str = ""
    attached_to: str | None = None
    cast_from_madness: bool = False

    @classmethod
    def from_instance(cls, instance_id: str, catalog: CardCatalog,
                      state: dict[str, Any] | None = None,
                      controller: str = "") -> "CardView":
        card = catalog.card(instance_id)
        return cls(
            instance_id=instance_id,
            base_id=card.base_id,
            name=card.name,
            card_type=card.card_type,
            subtype=card.subtype,
            colors=card.colors,
            mana_cost=card.mana_cost,
            power=card.power,
            toughness=card.toughness,
            keywords=tuple(dict.fromkeys((*card.keywords,
                                         *tuple(state.get("temporary_keywords", ()))))) if state else card.keywords,
            effect=card.effect,
            owner=controller,
            controller=controller,
            attached_to=state.get("attached_to") if state else None,
            cast_from_madness=bool(state.get("cast_from_madness", False)) if state else False,
            tapped=bool(state.get("tapped", False)) if state else False,
            summoning_sick=(bool(state.get("summoning_sick", False))
                            and "Creature" in card.card_type) if state else False,
            damage=int(state.get("damage", 0)) if state else 0,
            power_modifier=int(state.get("power", card.power or 0)) - (card.power or 0) if state and "power" in state else 0,
            toughness_modifier=int(state.get("toughness", card.toughness or 0)) - (card.toughness or 0) if state and "toughness" in state else 0,
        )


@dataclass(frozen=True)
class PlayerView:
    """Read-only projection of a single player's visible state."""
    player_id: str
    life: int
    hand_count: int
    library_count: int
    land_played: bool
    battlefield: tuple[CardView, ...]
    graveyard_count: int
    exile_count: int
    graveyard: tuple[CardView, ...] = ()
    mana_pool: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceSummary:
    """Visible, server-authoritative player resources for the tabletop header."""

    life: int
    hand_count: int
    library_count: int
    graveyard_count: int
    exile_count: int
    land_played: bool
    permanent_count: int
    mana_sources: Mapping[str, int]


@dataclass(frozen=True)
class StackView:
    """Read-only projection of an active spell or ability on the stack."""
    stack_item_id: str
    item_type: str
    source: CardView
    controller: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class GameView:
    """
    Complete read-only projection of the visible game state.

    Used by the GUI layer to render the tabletop and determine which
    actions are legally available to the player.
    """
    player_id: str
    opponent_id: str
    lifecycle: str
    phase: str
    phase_label: str
    turn: int
    active_player: str
    priority_holder: str | None
    has_priority: bool
    is_active_player: bool
    player: PlayerView
    opponent: PlayerView
    hand: tuple[CardView, ...]
    stack: tuple[StackView, ...]
    combat: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_state(cls, player_id: str, state: dict[str, Any],
                   catalog: CardCatalog) -> "GameView":
        life_totals = state.get("life_totals", {})
        opponent_id = next((pid for pid in life_totals if pid != player_id), "Opponent")

        def player_view(pid: str) -> PlayerView:
            permanent_records = state.get("battlefield", {}).get(pid, ())
            battlefield = tuple(
                CardView.from_instance(item["id"], catalog, item, controller=pid)
                for item in permanent_records
            )
            return PlayerView(
                player_id=pid,
                life=int(life_totals.get(pid, 20)),
                hand_count=int(state.get("hand_counts", {}).get(pid, 0)),
                library_count=int(state.get("library_counts", {}).get(pid, 0)),
                land_played=bool(state.get("land_played_this_turn", False)),
                battlefield=battlefield,
                graveyard_count=len(state.get("graveyard", {}).get(pid, ())),
                exile_count=len(state.get("exile", {}).get(pid, ())),
                graveyard=tuple(
                    CardView.from_instance(card_id, catalog, controller=pid)
                    for card_id in state.get("graveyard", {}).get(pid, ())
                ),
                mana_pool=dict(state.get("mana_pools", {}).get(pid, {})),
            )

        hand = tuple(
            CardView.from_instance(card_id, catalog, controller=player_id)
            for card_id in state.get("hand", ())
        ) + tuple(
            CardView.from_instance(card_id, catalog, controller=player_id,
                                   state={"cast_from_madness": True})
            for card_id in state.get("madness", ())
        )
        stack = tuple(
            StackView(
                stack_item_id=item["stack_item_id"],
                item_type=item["item_type"],
                source=CardView.from_instance(item["source"], catalog, controller=item["controller"]),
                controller=item["controller"],
                targets=tuple(item.get("targets", ())),
            )
            for item in state.get("stack", ())
        )
        phase = str(state.get("phase", "UNTAP"))
        active_player = str(state.get("active_player", ""))
        priority_holder = state.get("priority_holder")
        return cls(
            player_id=player_id,
            opponent_id=opponent_id,
            lifecycle=str(state.get("lifecycle", "LOBBY")),
            phase=phase,
            phase_label=PHASE_LABELS.get(phase, phase.replace("_", " ").title()),
            turn=int(state.get("turn", 1)),
            active_player=active_player,
            priority_holder=priority_holder,
            has_priority=priority_holder == player_id,
            is_active_player=active_player == player_id,
            player=player_view(player_id),
            opponent=player_view(opponent_id),
            hand=hand,
            stack=stack,
            combat=dict(state.get("combat", {})),
        )


def _all_cards(view: GameView) -> tuple[CardView, ...]:
    return (*view.hand, *view.player.battlefield, *view.opponent.battlefield)


def card_border_color(card: CardView) -> str:
    """Return the semantic outline color for a card tile from catalog colors."""
    colors = {color.upper() for color in card.colors}
    if len(colors) > 1:
        return MULTICOLOR_CARD_BORDER
    if len(colors) == 1:
        return CARD_BORDER_COLORS.get(colors.pop(), COLORLESS_CARD_BORDER)
    return COLORLESS_CARD_BORDER


def resource_summary(player: PlayerView) -> ResourceSummary:
    """Project untapped mana sources plus the authoritative floating mana pool."""
    mana_sources: dict[str, int] = dict(player.mana_pool)
    for permanent in player.battlefield:
        if (permanent.tapped
                or ("Creature" in permanent.card_type and permanent.summoning_sick)):
            continue
        output = MANA_SOURCE_OUTPUTS.get(permanent.base_id)
        if output is None:
            continue
        color, amount = output
        mana_sources[color] = mana_sources.get(color, 0) + amount
    return ResourceSummary(
        life=player.life,
        hand_count=player.hand_count,
        library_count=player.library_count,
        graveyard_count=player.graveyard_count,
        exile_count=player.exile_count,
        land_played=player.land_played,
        permanent_count=len(player.battlefield),
        mana_sources=mana_sources,
    )


def phase_neighbors(phase: str) -> tuple[str, str, str]:
    """Return protocol-order previous, current, and next phase identifiers."""
    phases = tuple(PHASE_LABELS)
    try:
        index = phases.index(phase)
    except ValueError:
        return phase, phase, phase
    return phases[index - 1], phase, phases[(index + 1) % len(phases)]


def bounded_activity_history(history: Sequence[str], message: str,
                             *, limit: int = 250) -> tuple[str, ...]:
    """Append one display-safe activity entry and retain only the newest items."""
    if limit < 1:
        raise ValueError("Activity history limit must be at least one.")
    normalized = " ".join(str(message).splitlines()).strip() or "Event"
    return (*tuple(history), normalized)[-limit:]


def selected_legal_attackers(view: GameView,
                             selected_ids: Sequence[str]) -> tuple[CardView, ...]:
    selected = set(selected_ids)
    pacified = {card.attached_to for card in (*view.player.battlefield,
                                               *view.opponent.battlefield)
                if card.base_id == "pacifism"}
    return tuple(
        card for card in view.player.battlefield
        if card.instance_id in selected
        and "Creature" in card.card_type
        and not card.tapped
        and (not card.summoning_sick or "Haste" in card.keywords)
        and "Defender" not in card.keywords
        and card.instance_id not in pacified
    )


def selected_legal_blockers(view: GameView,
                            selected_ids: Sequence[str]) -> tuple[CardView, ...]:
    selected = set(selected_ids)
    pacified = {card.attached_to for card in (*view.player.battlefield,
                                               *view.opponent.battlefield)
                if card.base_id == "pacifism"}
    return tuple(
        card for card in view.player.battlefield
        if card.instance_id in selected
        and "Creature" in card.card_type
        and not card.tapped
        and card.instance_id not in pacified
    )


def available_actions(view: GameView, selected_ids: list[str] | tuple[str, ...]) -> frozenset[str]:
    """Return only controls that can produce a supported request in this snapshot."""
    actions = {"concede"}
    if view.lifecycle == "MULLIGAN":
        return frozenset((*actions, "keep", "mulligan"))
    if view.lifecycle != "PLAYING":
        return frozenset(actions)
    if view.has_priority:
        actions.add("pass_priority")

    selected = set(selected_ids)
    selected_hand = [card for card in view.hand if card.instance_id in selected]
    main_phase = view.phase in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}

    if len(selected_hand) == 1:
        card = selected_hand[0]
        if (card.card_type == "Land" and view.has_priority
                and view.is_active_player and main_phase
                and not view.player.land_played and not view.stack):
            actions.add("play_land")
        elif card.card_type != "Land" and view.has_priority:
            supported = (card.card_type not in {"Instant", "Sorcery"}
                         or card.base_id in SUPPORTED_SPELL_EFFECTS)
            timing = card.card_type == "Instant" or card.cast_from_madness or (
                view.is_active_player and main_phase and not view.stack)
            if supported and timing:
                actions.add("cast_spell")
    selected_own = [card for card in view.player.battlefield if card.instance_id in selected]
    if (len(selected_own) == 1 and view.has_priority
            and selected_own[0].base_id in ACTIVATED_ABILITY_CARDS
            and not selected_own[0].tapped
            and (not selected_own[0].summoning_sick
                 or "Creature" not in selected_own[0].card_type
                 or selected_own[0].base_id == "troll_ascetic")):
        actions.add("activate_ability")

    discard_needed = max(0, view.player.hand_count - 7)
    if view.phase == "CLEANUP" and discard_needed > 0 and len(selected_hand) == discard_needed:
        actions.add("discard")

    if view.phase == "DECLARE_ATTACKERS" and view.is_active_player:
        actions.add("declare_no_attackers")
        if selected_legal_attackers(view, selected_ids):
            actions.add("declare_attackers")
    if view.phase == "DECLARE_BLOCKERS" and not view.is_active_player:
        if view.combat.get("attackers"):
            actions.add("declare_no_blockers")
        if view.combat.get("attackers") and selected_legal_blockers(view, selected_ids):
            actions.add("declare_blockers")
    if view.phase == "ASSIGN_DAMAGE_ORDER" and view.is_active_player:
        actions.add("assign_damage_order")
    return frozenset(actions)


def legal_target_options(view: GameView, card: CardDefinition) -> tuple[tuple[str, str], ...]:
    permanents = (*view.player.battlefield, *view.opponent.battlefield)
    if card.base_id in {"lightning_bolt", "shock", "searing_spear", "skullcrack",
                        "rift_bolt", "incinerate", "healing_salve"}:
        players = ((view.opponent_id, f"{view.opponent_id} — opponent"),
                   (view.player_id, f"{view.player_id} — you"))
        return players + tuple((item.instance_id, f"{item.name} — permanent")
                               for item in permanents if "Creature" in item.card_type)
    if card.base_id in {"lava_spike", "mind_rot"}:
        return ((view.opponent_id, f"{view.opponent_id} — opponent"),
                (view.player_id, f"{view.player_id} — you"))
    if card.base_id in {"flame_slash", "unsummon", "giant_growth",
                        "vines_of_vastwood", "swords_to_plowshares",
                        "path_to_exile", "pacifism"}:
        return tuple((item.instance_id, f"{item.name} — creature") for item in permanents
                     if "Creature" in item.card_type)
    if card.base_id in {"doom_blade", "terror"}:
        return tuple(
            (item.instance_id, f"{item.name} — creature")
            for item in permanents
            if "Creature" in item.card_type
            and "B" not in item.colors
            and (card.base_id != "terror" or "Artifact" not in item.card_type)
            and not any(keyword == "Protection from black" for keyword in item.keywords)
        )
    if card.base_id == "raise_dead":
        return tuple(
            (item.instance_id, f"{item.name} — your graveyard")
            for item in view.player.graveyard
            if "Creature" in item.card_type
        )
    if card.base_id == "gravedigger":
        return tuple((item.instance_id, f"{item.name} — your graveyard")
                     for item in view.player.graveyard if "Creature" in item.card_type)
    if card.base_id == "naturalize":
        return tuple((item.instance_id, f"{item.name} — permanent") for item in permanents
                     if "Artifact" in item.card_type or "Enchantment" in item.card_type)
    if card.base_id in {"counterspell", "cancel", "mana_leak"}:
        return tuple((item.stack_item_id, f"{item.source.name} — stack") for item in view.stack)
    if card.base_id == "negate":
        return tuple((item.stack_item_id, f"{item.source.name} — stack") for item in view.stack
                     if "Creature" not in item.source.card_type)
    return ()


class GuiEventBridge:
    """Queues callbacks until Tk's main thread drains them."""

    def __init__(self):
        self._queue: queue.SimpleQueue[tuple[Callable, tuple, dict]] = queue.SimpleQueue()

    def post(self, callback: Callable, *args, **kwargs) -> None:
        self._queue.put((callback, args, kwargs))

    def drain(self, on_error: Callable[[Exception], None] | None = None,
              *, max_callbacks: int | None = 32) -> int:
        count = 0
        while max_callbacks is None or count < max_callbacks:
            try:
                callback, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                return count
            try:
                callback(*args, **kwargs)
            except Exception as exc:
                if on_error is None:
                    raise
                on_error(exc)
            count += 1
        return count
