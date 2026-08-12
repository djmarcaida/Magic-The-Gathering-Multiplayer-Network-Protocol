"""Single-threaded authoritative MTGNP game engine."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from time import monotonic
from typing import Any

from common.cards import CardCatalog, DeckValidationError
from common.pdus import PDUValidationError, validate_pdu
from server.game_state import GameState, Lifecycle, Phase, PermanentState, StackItem
from server.priority_stack import PriorityError, PriorityOutcome, PriorityStack


@dataclass(frozen=True)
class Outbound:
    recipient: str | None
    pdu: dict[str, object]


class ActionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GameEngine:
    """Owns all mutable game data. Call :meth:`process` from one game-loop thread."""

    def __init__(self, catalog: CardCatalog, rng: Random | None = None,
                 priority_timeout_ms: int = 60_000):
        self.catalog = catalog
        self.rng = rng or Random()
        self.priority_timeout_ms = priority_timeout_ms
        self.state: GameState | None = None
        self.ready_by_seat: dict[str, tuple[str, tuple[str, ...]]] = {}
        self.request_tokens: dict[str, int] = {}
        self.server_seq_num = 1
        self._stack_counter = 1
        self.priority: PriorityStack | None = None
        self.priority_deadline: float | None = None

    def _pdu(self, pdu_type: str, **fields: object) -> dict[str, object]:
        pdu = {"type": pdu_type, "seq_num": self.server_seq_num, **fields}
        self.server_seq_num += 1
        return pdu

    def _error(self, seat: str, code: str, message: str,
               rejected: dict[str, object] | None) -> list[Outbound]:
        outgoing = [Outbound(seat, self._pdu("ERROR", code=code, message=message,
                                             rejected_action=rejected))]
        if (self.state is not None and self.state.priority_holder is not None
                and self.seat_for_player(self.state.priority_holder) == seat
                and self.state.priority_token is not None):
            self.priority_deadline = monotonic() + self.priority_timeout_ms / 1000
            outgoing.append(Outbound(seat, {
                "type": "PRIORITY_GRANT",
                "seq_num": self.state.priority_token,
                "player_id": self.state.priority_holder,
                "time_limit_ms": self.priority_timeout_ms,
            }))
        elif code == "STALE_ACTION" and self._seat_has_direct_request(seat):
            update = self.snapshot_updates(seats=(seat,))[0]
            self.request_tokens[seat] = update.pdu["seq_num"]
            outgoing.append(update)
        return outgoing

    def _seat_has_direct_request(self, seat: str) -> bool:
        if self.state is None:
            return False
        player_id = self.player_for_seat(seat)
        active = self.state.active_player
        if self.state.phase in {Phase.DECLARE_ATTACKERS, Phase.ASSIGN_DAMAGE_ORDER}:
            return player_id == active
        if self.state.phase == Phase.DECLARE_BLOCKERS:
            return player_id != active
        if self.state.phase == Phase.CLEANUP:
            return (player_id == active
                    and len(self.state.players[active].hand) > 7)
        return False

    def protocol_error(self, seat: str, code: str, message: str) -> list[Outbound]:
        return self._error(seat, code, message, None)

    def player_for_seat(self, seat: str) -> str:
        if self.state and seat in self.state.seats:
            return self.state.seats[seat]
        try:
            return self.ready_by_seat[seat][0]
        except KeyError as exc:
            raise ActionError("ILLEGAL_ACTION", "seat has no registered player") from exc

    def seat_for_player(self, player_id: str) -> str:
        if self.state:
            return next(seat for seat, pid in self.state.seats.items() if pid == player_id)
        return next(seat for seat, ready in self.ready_by_seat.items() if ready[0] == player_id)

    def process(self, seat_id: str, pdu: dict[str, object]) -> list[Outbound]:
        try:
            message = validate_pdu(pdu, direction="C->S")
            if message["type"] == "PING":
                return [Outbound(seat_id, {"type": "PONG", "seq_num": message["seq_num"],
                                           "timestamp": message["timestamp"]})]
            if message["type"] == "PLAYER_READY":
                return self._handle_ready(seat_id, message)
            if self.state is None:
                raise ActionError("ILLEGAL_ACTION", "game has not started")
            handlers = {
                "MULLIGAN_CHOICE": self._handle_mulligan,
                "CONCEDE": self._handle_concede,
                "PRIORITY_PASS": self._handle_priority_pass,
                "PLAY_LAND": self._handle_play_land,
                "CAST_SPELL": self._handle_cast_spell,
                "DECLARE_ATTACKERS": self._handle_attackers,
                "DECLARE_BLOCKERS": self._handle_blockers,
                "ASSIGN_DAMAGE_ORDER": self._handle_damage_order,
                "DISCARD": self._handle_discard,
                "ACTIVATE_ABILITY": self._handle_activate_ability,
                "TRIGGER_ORDER_RESPONSE": self._handle_unavailable,
                "TRIGGER_CHOICE_RESPONSE": self._handle_unavailable,
            }
            return handlers[message["type"]](seat_id, message)
        except (PDUValidationError, ActionError, PriorityError) as exc:
            return self._error(seat_id, exc.code, str(exc), pdu)

    def _handle_ready(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        player_id = pdu["player_id"]
        deck = pdu["deck_list"]
        if not isinstance(player_id, str) or not player_id.strip():
            raise ActionError("DUPLICATE_ID", "player_id must be a non-empty string")
        for other_seat, (other_id, _) in self.ready_by_seat.items():
            if other_seat != seat and other_id == player_id:
                raise ActionError("DUPLICATE_ID", "player_id is already seated")
        if not isinstance(deck, list) or not all(isinstance(x, str) for x in deck):
            raise ActionError("ILLEGAL_DECK", "deck_list must be a list of card IDs")
        try:
            valid_deck = self.catalog.validate_deck(deck)
        except DeckValidationError as exc:
            raise ActionError("ILLEGAL_DECK", str(exc)) from exc
        if self.state is not None:
            current = self.state.seats.get(seat)
            if current == player_id:
                return self.snapshot_updates(seats=(seat,))
            raise ActionError("ILLEGAL_ACTION", "cannot change player identity during a game")
        self.ready_by_seat[seat] = (player_id, valid_deck)
        if len(self.ready_by_seat) < 2:
            ready_ids = {pid for pid, _ in self.ready_by_seat.values()}
            waiting = [f"player_{i}" for i in range(1, 3)
                       if f"player_{i}" not in ready_ids]
            if not waiting:
                waiting = ["waiting"]
            return [Outbound(seat, self._pdu("GAME_STATE_UPDATE", state={
                "lifecycle": "LOBBY", "players_ready": len(self.ready_by_seat),
                "waiting_for": waiting,
            }))]
        seats = tuple(self.ready_by_seat)
        players = tuple(self.ready_by_seat[s][0] for s in seats)
        decks = {pid: list(deck_ids) for pid, deck_ids in self.ready_by_seat.values()}
        first = self.rng.choice(players)
        self.state = GameState.new(players, decks, first, self.rng)
        self.state.seats = {seat_id: self.ready_by_seat[seat_id][0] for seat_id in seats}
        updates = self.snapshot_updates()
        for update in updates:
            self.request_tokens[update.recipient] = update.pdu["seq_num"]
        return updates

    def snapshot_updates(self, seats: tuple[str, ...] | None = None) -> list[Outbound]:
        if self.state is None:
            return []
        targets = seats or tuple(self.state.seats)
        updates = []
        for seat in targets:
            updates.append(Outbound(seat, self._pdu(
                "GAME_STATE_UPDATE",
                state=self.state.visible_to(self.state.seats[seat], self.catalog))))
        return updates

    def _require_token(self, seat: str, pdu: dict[str, object]) -> None:
        if pdu["seq_num"] != self.request_tokens.get(seat):
            raise ActionError("STALE_ACTION", "action does not echo the current request token")

    def _handle_mulligan(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None
        if self.state.lifecycle != Lifecycle.MULLIGAN:
            raise ActionError("WRONG_PHASE", "mulligan choice is only valid during MULLIGAN")
        self._require_token(seat, pdu)
        player = self.state.players[self.player_for_seat(seat)]
        bottom = pdu["cards_to_bottom"]
        if not isinstance(pdu["keep"], bool) or not isinstance(bottom, list):
            raise ActionError("ILLEGAL_ACTION", "invalid mulligan choice fields")
        if pdu["keep"]:
            needed = min(player.mulligans, len(player.hand))
            if len(bottom) != needed or len(set(bottom)) != len(bottom) or any(x not in player.hand for x in bottom):
                raise ActionError("ILLEGAL_ACTION", f"keep requires exactly {needed} cards from hand to bottom")
            for card_id in bottom:
                player.hand.remove(card_id)
            player.library[0:0] = bottom
            player.kept = True
        else:
            player.library.extend(player.hand)
            player.hand.clear()
            self.rng.shuffle(player.library)
            player.hand.extend(player.library.pop() for _ in range(min(7, len(player.library))))
            player.mulligans += 1
        if all(p.kept for p in self.state.players.values()):
            self.state.lifecycle = Lifecycle.PLAYING
            return self._start_turn("MULLIGAN", increment_turn=False)
        updates = self.snapshot_updates()
        for update in updates:
            if not self.state.players[self.state.seats[update.recipient]].kept:
                self.request_tokens[update.recipient] = update.pdu["seq_num"]
        return updates

    def _handle_concede(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        loser = self.player_for_seat(seat)
        if pdu["player_id"] != loser:
            raise ActionError("ILLEGAL_ACTION", "cannot concede for another player")
        return self._finish(self.state.opponent_of(loser), loser, "CONCEDE")

    def _finish(self, winner: str, loser: str, reason: str) -> list[Outbound]:
        outgoing = []
        if self.state is not None:
            outgoing.extend(self.snapshot_updates())
        outgoing.append(Outbound(None, self._pdu("GAME_OVER", winner_id=winner,
                                                 loser_id=loser, reason=reason)))
        self.state = None
        self.ready_by_seat.clear()
        self.request_tokens.clear()
        self.priority = None
        self.priority_deadline = None
        return outgoing

    def connection_lost(self, seat: str) -> list[Outbound]:
        if self.state is None or seat not in self.state.seats:
            return []
        loser = self.state.seats[seat]
        return self._finish(self.state.opponent_of(loser), loser, "DISCONNECT")

    def reconnect(self, seat: str, player_id: str) -> list[Outbound]:
        if self.state is None or self.state.seats.get(seat) != player_id:
            raise ActionError("DUPLICATE_ID", "player ID does not own the reserved seat")
        return self.snapshot_updates(seats=(seat,))

    def _clear_priority(self) -> None:
        if self.state is not None:
            self.state.priority_holder = None
            self.state.priority_token = None
        if self.priority is not None:
            self.priority.holder = None
            self.priority.token = None
            self.priority.consecutive_passes = 0
        self.priority_deadline = None

    def _grant_priority(self, player_id: str, *, open_window: bool = False) -> list[Outbound]:
        assert self.state is not None
        seat = self.seat_for_player(player_id)
        grant = self._pdu("PRIORITY_GRANT", player_id=player_id,
                          time_limit_ms=self.priority_timeout_ms)
        token = grant["seq_num"]
        self.request_tokens[seat] = token
        self.state.priority_holder = player_id
        self.state.priority_token = token
        self.priority_deadline = monotonic() + self.priority_timeout_ms / 1000
        if self.priority is None:
            self.priority = PriorityStack(self.state.active_player,
                                          self.state.opponent_of(self.state.active_player),
                                          self.state.stack)
            self.priority.open(player_id, token)
        else:
            self.priority.active_player = self.state.active_player
            self.priority.non_active_player = self.state.opponent_of(self.state.active_player)
            if open_window:
                self.priority.open(player_id, token)
            else:
                self.priority.grant(player_id, token)
        return [Outbound(seat, grant), *self.snapshot_updates()]

    def expire_priority(self, now: float | None = None) -> list[Outbound]:
        """Treat an expired RFC priority window as a pass by its holder."""
        if (self.state is None or self.priority is None or self.priority_deadline is None
                or (monotonic() if now is None else now) < self.priority_deadline
                or self.state.priority_holder is None or self.state.priority_token is None):
            return []
        seat = self.seat_for_player(self.state.priority_holder)
        return self._handle_priority_pass(seat, {
            "type": "PRIORITY_PASS", "seq_num": self.state.priority_token,
        })

    def _handle_unavailable(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        raise ActionError("ILLEGAL_ACTION", "no pending trigger request")

    # Gameplay handlers are below; each validates fully before mutation.

    def _handle_priority_pass(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None and self.priority is not None
        player = self.player_for_seat(seat)
        outcome = self.priority.pass_priority(player, pdu["seq_num"])
        if outcome == PriorityOutcome.TRANSFER:
            return self._grant_priority(self.state.opponent_of(player))
        if outcome == PriorityOutcome.RESOLVE_TOP:
            outgoing = self._resolve_top()
            if self.state is not None:
                outgoing.extend(self._grant_priority(self.state.active_player))
            return outgoing
        return self.advance_step()

    def _handle_play_land(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None and self.priority is not None
        player_id = self.player_for_seat(seat)
        player = self.state.players[player_id]
        card_id = pdu["card_id"]
        if self.state.phase not in {Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN}:
            raise ActionError("WRONG_PHASE", "lands can only be played during your main phase")
        if self.state.priority_holder != player_id:
            raise ActionError("NOT_YOUR_PRIORITY", "player does not hold priority")
        if player.land_played:
            raise ActionError("ILLEGAL_ACTION", "one land may be played each turn")
        if card_id not in player.hand or self.catalog.get(card_id).card_type != "Land":
            raise ActionError("ILLEGAL_ACTION", "card is not a land in your hand")
        if self.state.stack:
            raise ActionError("ILLEGAL_ACTION", "a land may be played only while the stack is empty")
        self.priority.act(player_id, pdu["seq_num"])
        player.hand.remove(card_id)
        player.battlefield.append(PermanentState(card_id, player_id, player_id,
                                                  summoning_sick=False))
        player.land_played = True
        return self._grant_priority(player_id)

    def _handle_cast_spell(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None and self.priority is not None
        player_id = self.player_for_seat(seat)
        if self.state.priority_holder != player_id:
            raise ActionError("NOT_YOUR_PRIORITY", "player does not hold priority")
        self._require_token(seat, pdu)
        player = self.state.players[player_id]
        card_id = pdu["card_id"]
        if card_id not in player.hand:
            raise ActionError("ILLEGAL_ACTION", "spell is not in your hand")
        card = self.catalog.get(card_id)
        if card.card_type == "Land":
            raise ActionError("ILLEGAL_ACTION", "lands are played, not cast")
        if card.card_type != "Instant" and (
                player_id != self.state.active_player
                or self.state.phase not in {Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN}
                or self.state.stack):
            raise ActionError("WRONG_PHASE", "non-instant spells require your empty-stack main phase")
        supported_effects = {"lightning_bolt", "counterspell", "unsummon", "giant_growth", "rift_bolt", "ponder", "rampant_growth"}
        if card.card_type in {"Instant", "Sorcery"} and card.base_id not in supported_effects:
            raise ActionError("ILLEGAL_ACTION", "this baseline does not implement that spell effect")
        targets = pdu["targets"]
        if not isinstance(targets, list):
            raise ActionError("ILLEGAL_TARGET", "targets must be a list")
        self._validate_spell_targets(card.base_id, targets)
        sources = pdu["mana_payment"]
        if not isinstance(sources, dict):
            raise ActionError("INSUFFICIENT_MANA", "mana_payment must be a color-count object")
        permanents = self._validate_mana_payment(player_id, sources, dict(card.mana_cost))
        self.priority.act(player_id, pdu["seq_num"])
        for permanent in permanents:
            permanent.tapped = True
        player.hand.remove(card_id)
        item = StackItem(f"stk_{self._stack_counter}", "SPELL", card_id, player_id,
                         list(targets))
        self._stack_counter += 1
        self.priority.push(item)
        outgoing = [Outbound(None, self._pdu("STACK_PUSH", stack_item_id=item.stack_item_id,
                                              item_type=item.item_type, source=item.source,
                                              targets=item.targets, controller=item.controller)),
                    *self._grant_priority(player_id)]
        return outgoing

    def _handle_attackers(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None
        player_id = self.player_for_seat(seat)
        raw_attackers = pdu["attackers"]
        if self.state.phase != Phase.DECLARE_ATTACKERS or player_id != self.state.active_player:
            raise ActionError("WRONG_PHASE", "attackers are declared by the active player")
        self._require_token(seat, pdu)
        if not isinstance(raw_attackers, list):
            raise ActionError("ILLEGAL_ACTION", "attackers must be a list")
        attackers: list[str] = []
        defender = self.state.opponent_of(player_id)
        for entry in raw_attackers:
            if isinstance(entry, str):
                card_id, target = entry, defender
            elif isinstance(entry, dict):
                card_id, target = entry.get("creature_id"), entry.get("target")
            else:
                raise ActionError("ILLEGAL_ACTION", "each attacker must identify a creature and target")
            if not isinstance(card_id, str) or target != defender:
                raise ActionError("ILLEGAL_TARGET", "attackers must target the opposing player")
            attackers.append(card_id)
        if len(set(attackers)) != len(attackers):
            raise ActionError("ILLEGAL_ACTION", "attackers must be unique")
        selected = []
        for card_id in attackers:
            permanent = self.state.permanent(card_id)
            card = self.catalog.get(card_id)
            if (permanent is None or permanent.controller != player_id
                    or "Creature" not in card.card_type or permanent.tapped
                    or (permanent.summoning_sick and "Haste" not in card.keywords)
                    or "Defender" in card.keywords):
                raise ActionError("ILLEGAL_ACTION", f"illegal attacker: {card_id}")
            selected.append(permanent)
        self.state.combat.attackers = list(attackers)
        for permanent in selected:
            if "Vigilance" not in self.catalog.get(permanent.card_id).keywords:
                permanent.tapped = True
        if not attackers:
            return self._enter_priority_phase(Phase.END_OF_COMBAT)
        return self._grant_priority(player_id, open_window=True)

    def _handle_blockers(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None
        player_id = self.player_for_seat(seat)
        raw_blockers = pdu["blockers"]
        if self.state.phase != Phase.DECLARE_BLOCKERS or player_id == self.state.active_player:
            raise ActionError("WRONG_PHASE", "blockers are declared by the defending player")
        self._require_token(seat, pdu)
        if isinstance(raw_blockers, dict):
            blockers = raw_blockers
        elif isinstance(raw_blockers, list):
            blockers: dict[str, list[str]] = {}
            for entry in raw_blockers:
                if not isinstance(entry, dict):
                    raise ActionError("ILLEGAL_ACTION", "each blocker must identify a creature and attacker")
                blocker_id = entry.get("creature_id")
                attacker_id = entry.get("blocking_id")
                if not isinstance(blocker_id, str) or not isinstance(attacker_id, str):
                    raise ActionError("ILLEGAL_ACTION", "blocker IDs must be strings")
                blockers.setdefault(attacker_id, []).append(blocker_id)
        else:
            raise ActionError("ILLEGAL_ACTION", "blockers must be a list")
        if any(a not in self.state.combat.attackers for a in blockers):
            raise ActionError("ILLEGAL_TARGET", "blockers must reference declared attackers")
        used: set[str] = set()
        normalized: dict[str, list[str]] = {}
        for attacker, blocker_ids in blockers.items():
            if not isinstance(blocker_ids, list):
                raise ActionError("ILLEGAL_ACTION", "each blocker group must be a list")
            for card_id in blocker_ids:
                permanent = self.state.permanent(card_id)
                card = self.catalog.get(card_id)
                if (card_id in used or permanent is None or permanent.controller != player_id
                        or permanent.tapped or "Creature" not in card.card_type):
                    raise ActionError("ILLEGAL_ACTION", f"illegal blocker: {card_id}")
                used.add(card_id)
            normalized[attacker] = list(blocker_ids)
        self.state.combat.blockers = normalized
        return self._grant_priority(self.state.active_player, open_window=True)

    def _handle_damage_order(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None
        player_id = self.player_for_seat(seat)
        attacker = pdu["attacker_id"]
        order = pdu["blocker_order"]
        expected = self.state.combat.blockers.get(attacker, [])
        self._require_token(seat, pdu)
        if (self.state.phase != Phase.ASSIGN_DAMAGE_ORDER or player_id != self.state.active_player
                or not isinstance(order, list) or len(order) != len(expected)
                or set(order) != set(expected)):
            raise ActionError("ILLEGAL_ACTION", "damage order must contain each assigned blocker once")
        self.state.combat.damage_order[attacker] = list(order)
        required = {attacker_id for attacker_id, blockers in self.state.combat.blockers.items()
                    if len(blockers) > 1}
        if required.issubset(self.state.combat.damage_order):
            return self._grant_priority(player_id, open_window=True)
        outgoing = self.snapshot_updates()
        update = next(x for x in outgoing if x.recipient == seat)
        self.request_tokens[seat] = update.pdu["seq_num"]
        return outgoing

    def _handle_discard(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        assert self.state is not None
        player_id = self.player_for_seat(seat)
        player = self.state.players[player_id]
        cards = pdu["card_ids"]
        needed = max(0, len(player.hand) - 7)
        if self.state.phase != Phase.CLEANUP or player_id != self.state.active_player:
            raise ActionError("WRONG_PHASE", "discard is required only during cleanup")
        self._require_token(seat, pdu)
        if (not isinstance(cards, list) or not 1 <= len(cards) <= needed
                or len(set(cards)) != len(cards) or any(x not in player.hand for x in cards)):
            raise ActionError("ILLEGAL_ACTION", f"must discard between 1 and {needed} cards from hand")
        for card_id in cards:
            player.hand.remove(card_id)
            player.graveyard.append(card_id)
        outgoing = self.snapshot_updates()
        if len(player.hand) > 7:
            update = next(x for x in outgoing if x.recipient == seat)
            self.request_tokens[seat] = update.pdu["seq_num"]
            return outgoing
        outgoing.extend(self._start_turn(Phase.CLEANUP.value, increment_turn=True))
        return outgoing

    def _handle_activate_ability(self, seat: str, pdu: dict[str, object]) -> list[Outbound]:
        player_id = self.player_for_seat(seat)
        if self.state.priority_holder != player_id:
            raise ActionError("NOT_YOUR_PRIORITY", "player does not hold priority")
        raise ActionError("ILLEGAL_ACTION", "this baseline does not implement this PDU type")

    def _resolve_top(self) -> list[Outbound]:
        assert self.state is not None and self.priority is not None
        item = self.priority.pop()
        card = self.catalog.get(item.source)
        base = card.base_id
        result = "RESOLVED"
        changes: list[dict[str, object]] = []
        trigger_pushed: StackItem | None = None
        if item.item_type == "TRIGGER_ABILITY" and base == "gray_merchant":
            devotion = sum(self.catalog.get(p.card_id).mana_cost.get("B", 0)
                           for p in self.state.players[item.controller].battlefield)
            if devotion > 0:
                self.state.players[self.state.opponent_of(item.controller)].life -= devotion
                self.state.players[item.controller].life += devotion
                changes.append({"change_type": "GRAY_MERCHANT", "amount": devotion})
        elif not self._targets_still_legal(base, item.targets):
            result = "FIZZLE"
        elif base == "lightning_bolt" or base == "rift_bolt":
            target = item.targets[0]
            if "player_" in target:
                self.state.players[target].life -= 3
            else:
                self.state.permanent(target).damage += 3
            changes.append({"change_type": "DAMAGE", "target": target, "amount": 3})
        elif base == "ponder":
            player = self.state.players[item.controller]
            if player.library:
                player.hand.append(player.library.pop())
            changes.append({"change_type": "CARD_DRAWN", "player": item.controller})
        elif base == "rampant_growth":
            land_id = self._fetch_basic_land(item.controller)
            if land_id:
                self.state.players[item.controller].battlefield.append(
                    PermanentState(land_id, item.controller, item.controller, tapped=True))
                changes.append({"change_type": "ENTERED_BATTLEFIELD", "card_id": land_id, "tapped": True})
            else:
                result = "FIZZLE"
        elif base == "counterspell":
            target_id = item.targets[0]
            target = next((x for x in self.state.stack if x.stack_item_id == target_id), None)
            if target is None:
                result = "FIZZLE"
            else:
                self.state.stack = [i for i in self.state.stack if i.stack_item_id != target_id]
                self.state.players[target.controller].graveyard.append(target.source)
                changes.append({"change_type": "COUNTERED", "stack_item_id": target_id})
        elif base == "unsummon":
            permanent = self.state.permanent(item.targets[0])
            self.state.players[permanent.controller].battlefield.remove(permanent)
            self.state.players[permanent.owner].hand.append(permanent.card_id)
            changes.append({"change_type": "RETURNED_TO_HAND", "card_id": permanent.card_id})
        elif base == "giant_growth":
            permanent = self.state.permanent(item.targets[0])
            permanent.power_modifier += 3
            permanent.toughness_modifier += 3
            changes.append({"change_type": "MODIFIED", "card_id": permanent.card_id,
                            "power": 3, "toughness": 3})
        elif "Creature" in card.card_type or card.card_type in {"Artifact", "Enchantment"}:
            self.state.players[item.controller].battlefield.append(
                PermanentState(item.source, item.controller, item.controller, tapped=False))
            changes.append({"change_type": "ENTERED_BATTLEFIELD", "card_id": item.source})
            if base == "gray_merchant":
                trigger_pushed = StackItem(f"stk_{self._stack_counter}", "TRIGGER_ABILITY",
                                           item.source, item.controller, [])
                self._stack_counter += 1
                self.priority.push(trigger_pushed)
        if item.item_type == "SPELL" and card.card_type in {"Instant", "Sorcery"}:
            self.state.players[item.controller].graveyard.append(item.source)
        dead = self._state_based_actions()
        changes.extend({"change_type": "DIED", "card_id": card_id} for card_id in dead)
        outgoing = [Outbound(None, self._pdu("STACK_RESOLVE", stack_item_id=item.stack_item_id,
                                             result=result, state_changes=changes))]
        if trigger_pushed is not None:
            outgoing.append(Outbound(None, self._pdu(
                "STACK_PUSH", stack_item_id=trigger_pushed.stack_item_id,
                item_type="TRIGGER_ABILITY", source=trigger_pushed.source,
                targets=[], controller=trigger_pushed.controller)))
        zero_life = [pid for pid, player in self.state.players.items() if player.life <= 0]
        if zero_life:
            if len(zero_life) == 2:
                winner = self.state.opponent_of(self.state.active_player)
                loser = self.state.active_player
            else:
                loser = zero_life[0]
                winner = self.state.opponent_of(loser)
            outgoing.extend(self._finish(winner, loser, "LIFE_ZERO"))
            return outgoing
        if self.state is not None:
            outgoing.extend(self.snapshot_updates())
        return outgoing

    def _validate_spell_targets(self, base_id: str, targets: list[str]) -> None:
        assert self.state is not None
        if base_id in {"lightning_bolt", "rift_bolt"}:
            target = targets[0] if len(targets) == 1 else None
            permanent = self.state.permanent(target) if target is not None else None
            if (target not in self.state.players
                    and (permanent is None
                         or "Creature" not in self.catalog.get(permanent.card_id).card_type)):
                raise ActionError("ILLEGAL_TARGET", "spell requires a player or creature target")
        elif base_id in {"unsummon", "giant_growth"}:
            if len(targets) != 1 or self.state.permanent(targets[0]) is None:
                raise ActionError("ILLEGAL_TARGET", "spell requires a creature target")
            if "Creature" not in self.catalog.get(targets[0]).card_type:
                raise ActionError("ILLEGAL_TARGET", "target is not a creature")
        elif base_id == "counterspell":
            if len(targets) != 1 or not any(x.stack_item_id == targets[0] for x in self.state.stack):
                raise ActionError("ILLEGAL_TARGET", "Counterspell requires a spell on the stack")
        elif targets:
            raise ActionError("ILLEGAL_TARGET", "this spell takes no target")

    def _targets_still_legal(self, base_id: str, targets: list[str]) -> bool:
        try:
            self._validate_spell_targets(base_id, targets)
            return True
        except ActionError:
            return False

    def _validate_mana_payment(self, player_id: str, payment: dict[str, object],
                               cost: dict[str, int]) -> list[PermanentState]:
        assert self.state is not None
        allowed = {"W", "U", "B", "R", "G", "C", "X"}
        if (any(key not in allowed for key in payment)
                or any(isinstance(value, bool) or not isinstance(value, int) or value < 0
                       for value in payment.values())):
            raise ActionError("INSUFFICIENT_MANA", "mana_payment has invalid colors or counts")
        for color in {"W", "U", "B", "R", "G", "C"}:
            if payment.get(color, 0) != cost.get(color, 0):
                raise ActionError("INSUFFICIENT_MANA", f"declared {color} payment does not match cost")
        if payment.get("X", 0) != cost.get("generic", 0):
            raise ActionError("INSUFFICIENT_MANA", "declared generic payment does not match cost")
        pool: dict[str, list[tuple[PermanentState, int]]] = {key: [] for key in allowed - {"X"}}
        for permanent in self.state.players[player_id].battlefield:
            if permanent.tapped:
                continue
            base = self.catalog.get(permanent.card_id).base_id
            produced = {"mountain": ("R", 1), "island": ("U", 1),
                        "forest": ("G", 1), "swamp": ("B", 1),
                        "plains": ("W", 1), "sol_ring": ("C", 2),
                        "llanowar_elves": ("G", 1), "elvish_mystic": ("G", 1)}.get(base)
            if produced:
                pool[produced[0]].append((permanent, produced[1]))
        chosen: list[PermanentState] = []
        for color in ("W", "U", "B", "R", "G", "C"):
            needed = cost.get(color, 0)
            while needed > 0 and pool[color]:
                permanent, amount = pool[color].pop(0)
                chosen.append(permanent)
                needed -= amount
            if needed > 0:
                raise ActionError("INSUFFICIENT_MANA", f"not enough untapped {color} sources")
        generic = cost.get("generic", 0)
        remaining = [source for sources in pool.values() for source in sources]
        while generic > 0 and remaining:
            permanent, amount = remaining.pop(0)
            if permanent not in chosen:
                chosen.append(permanent)
                generic -= amount
        if generic > 0:
            raise ActionError("INSUFFICIENT_MANA", "not enough untapped sources for generic cost")
        return chosen

    def _state_based_actions(self) -> list[str]:
        assert self.state is not None
        dead: list[str] = []
        for player in self.state.players.values():
            for permanent in list(player.battlefield):
                card = self.catalog.get(permanent.card_id)
                if card.toughness is not None and (card.toughness + permanent.toughness_modifier <= 0
                                                   or permanent.damage >= card.toughness + permanent.toughness_modifier):
                    player.battlefield.remove(permanent)
                    player.graveyard.append(permanent.card_id)
                    dead.append(permanent.card_id)
        return dead

    def resolve_combat_damage(self, first_strike: bool) -> list[Outbound]:
        assert self.state is not None
        events: list[dict[str, object]] = []
        active = self.state.active_player
        defender = self.state.opponent_of(active)
        for attacker_id in self.state.combat.attackers:
            attacker = self.state.permanent(attacker_id)
            if attacker is None:
                continue
            attacker_card = self.catalog.get(attacker_id)
            attacker_first = "First strike" in attacker_card.keywords
            attacker_double = "Double strike" in attacker_card.keywords
            attacker_deals = attacker_double or attacker_first == first_strike
            assigned_blocker_ids = self.state.combat.blockers.get(attacker_id, [])
            blockers = [self.state.permanent(x) for x in assigned_blocker_ids]
            blockers = [x for x in blockers if x is not None]
            if not assigned_blocker_ids and attacker_deals:
                amount = attacker_card.power + attacker.power_modifier
                self.state.players[defender].life -= amount
                events.append({"source": attacker_id, "target": defender, "amount": amount})
            elif assigned_blocker_ids:
                order_ids = self.state.combat.damage_order.get(attacker_id,
                                                                [x.card_id for x in blockers])
                remaining = attacker_card.power + attacker.power_modifier
                if attacker_deals:
                    for blocker_id in order_ids:
                        blocker = self.state.permanent(blocker_id)
                        if blocker is None or remaining <= 0:
                            continue
                        blocker_card = self.catalog.get(blocker_id)
                        lethal = max(0, blocker_card.toughness + blocker.toughness_modifier - blocker.damage)
                        amount = min(remaining, lethal)
                        if blocker_id == order_ids[-1]:
                            amount = remaining
                        blocker.damage += amount
                        remaining -= amount
                        events.append({"source": attacker_id, "target": blocker_id, "amount": amount})
                for blocker in blockers:
                    blocker_card = self.catalog.get(blocker.card_id)
                    blocker_first = "First strike" in blocker_card.keywords
                    blocker_double = "Double strike" in blocker_card.keywords
                    if blocker_double or blocker_first == first_strike:
                        amount = blocker_card.power + blocker.power_modifier
                        attacker.damage += amount
                        events.append({"source": blocker.card_id, "target": attacker_id, "amount": amount})
        dead = self._state_based_actions()
        result = Outbound(None, self._pdu("COMBAT_DAMAGE_RESULT", damage_events=events,
                                          life_totals={p: s.life for p, s in self.state.players.items()},
                                          creatures_died=dead))
        outgoing = [result]
        zero_life = [pid for pid, player in self.state.players.items() if player.life <= 0]
        if zero_life:
            if len(zero_life) == 2:
                loser = self.state.active_player
            else:
                loser = zero_life[0]
            outgoing.extend(self._finish(self.state.opponent_of(loser), loser, "LIFE_ZERO"))
            return outgoing
        outgoing.extend(self.snapshot_updates())
        return outgoing

    def _transition(self, old: str | Phase, new: Phase) -> Outbound:
        assert self.state is not None
        old_value = old.value if isinstance(old, Phase) else old
        self.state.phase = new
        return Outbound(None, self._pdu("PHASE_TRANSITION", from_phase=old_value,
                                        to_phase=new.value,
                                        active_player=self.state.active_player,
                                        turn=self.state.turn))

    def _enter_priority_phase(self, new: Phase) -> list[Outbound]:
        assert self.state is not None
        old = self.state.phase
        self._clear_priority()
        transition = self._transition(old, new)
        if new == Phase.DRAW:
            skip = self.state.turn == 1 and self.state.active_player == self.state.first_player
            if not skip:
                player = self.state.players[self.state.active_player]
                if not player.library:
                    return [transition, *self._finish(
                        self.state.opponent_of(player.player_id), player.player_id, "DECK_EMPTY")]
                player.hand.append(player.library.pop())
                return [transition, *self.snapshot_updates(),
                        *self._grant_priority(self.state.active_player, open_window=True)]
        return [transition, *self._grant_priority(self.state.active_player, open_window=True)]

    def _enter_declaration_phase(self, new: Phase) -> list[Outbound]:
        assert self.state is not None
        old = self.state.phase
        self._clear_priority()
        outgoing = [self._transition(old, new)]
        updates = self.snapshot_updates()
        for update in updates:
            self.request_tokens[update.recipient] = update.pdu["seq_num"]
        outgoing.extend(updates)
        return outgoing

    def _start_turn(self, old: str, *, increment_turn: bool) -> list[Outbound]:
        assert self.state is not None
        if increment_turn:
            self.state.active_player = self.state.opponent_of(self.state.active_player)
            self.state.turn += 1
        self._clear_priority()
        untap = self._transition(old, Phase.UNTAP)
        player = self.state.players[self.state.active_player]
        player.land_played = False
        for permanent in player.battlefield:
            permanent.tapped = False
            permanent.summoning_sick = False
        self.state.combat.attackers.clear()
        self.state.combat.blockers.clear()
        self.state.combat.damage_order.clear()
        outgoing = [untap, *self.snapshot_updates()]
        outgoing.extend(self._enter_priority_phase(Phase.UPKEEP))
        return outgoing

    def _has_first_strike_combatant(self) -> bool:
        assert self.state is not None
        combatants = set(self.state.combat.attackers)
        combatants.update(card_id for group in self.state.combat.blockers.values()
                          for card_id in group)
        return any(self.state.permanent(card_id) is not None
                   and ({"First strike", "Double strike"}
                        & set(self.catalog.get(card_id).keywords))
                   for card_id in combatants)

    def _enter_combat_damage(self, *, first_strike: bool) -> list[Outbound]:
        assert self.state is not None
        old = self.state.phase
        new = Phase.FIRST_STRIKE_DAMAGE if first_strike else Phase.COMBAT_DAMAGE
        self._clear_priority()
        outgoing = [self._transition(old, new)]
        outgoing.extend(self.resolve_combat_damage(first_strike=first_strike))
        if self.state is None:
            return outgoing
        if first_strike:
            outgoing.extend(self._grant_priority(self.state.active_player, open_window=True))
            return outgoing
        outgoing.extend(self._enter_priority_phase(Phase.END_OF_COMBAT))
        return outgoing

    def _after_blocker_window(self) -> list[Outbound]:
        assert self.state is not None
        if any(len(blockers) > 1 for blockers in self.state.combat.blockers.values()):
            return self._enter_declaration_phase(Phase.ASSIGN_DAMAGE_ORDER)
        if self._has_first_strike_combatant():
            return self._enter_combat_damage(first_strike=True)
        return self._enter_combat_damage(first_strike=False)

    def _enter_cleanup(self) -> list[Outbound]:
        assert self.state is not None
        old = self.state.phase
        self._clear_priority()
        transition = self._transition(old, Phase.CLEANUP)
        for player in self.state.players.values():
            for permanent in player.battlefield:
                permanent.damage = 0
                permanent.power_modifier = 0
                permanent.toughness_modifier = 0
        outgoing = [transition, *self.snapshot_updates()]
        active_seat = self.seat_for_player(self.state.active_player)
        if len(self.state.players[self.state.active_player].hand) > 7:
            update = next(x for x in outgoing if x.recipient == active_seat)
            self.request_tokens[active_seat] = update.pdu["seq_num"]
            return outgoing
        outgoing.extend(self._start_turn(Phase.CLEANUP.value, increment_turn=True))
        return outgoing

    def advance_step(self) -> list[Outbound]:
        assert self.state is not None
        old = self.state.phase
        if old == Phase.UNTAP:
            return self._enter_priority_phase(Phase.UPKEEP)
        if old == Phase.UPKEEP:
            return self._enter_priority_phase(Phase.DRAW)
        if old == Phase.DRAW:
            return self._enter_priority_phase(Phase.PRECOMBAT_MAIN)
        if old == Phase.PRECOMBAT_MAIN:
            return self._enter_priority_phase(Phase.BEGIN_COMBAT)
        if old == Phase.BEGIN_COMBAT:
            return self._enter_declaration_phase(Phase.DECLARE_ATTACKERS)
        if old == Phase.DECLARE_ATTACKERS:
            return self._enter_declaration_phase(Phase.DECLARE_BLOCKERS)
        if old == Phase.DECLARE_BLOCKERS:
            return self._after_blocker_window()
        if old == Phase.ASSIGN_DAMAGE_ORDER:
            if self._has_first_strike_combatant():
                return self._enter_combat_damage(first_strike=True)
            return self._enter_combat_damage(first_strike=False)
        if old == Phase.FIRST_STRIKE_DAMAGE:
            return self._enter_combat_damage(first_strike=False)
        if old == Phase.COMBAT_DAMAGE:
            return self._enter_priority_phase(Phase.END_OF_COMBAT)
        if old == Phase.END_OF_COMBAT:
            for player in self.state.players.values():
                for permanent in player.battlefield:
                    permanent.damage = 0
            self.state.combat.attackers.clear()
            self.state.combat.blockers.clear()
            self.state.combat.damage_order.clear()
            return self._enter_priority_phase(Phase.POSTCOMBAT_MAIN)
        if old == Phase.POSTCOMBAT_MAIN:
            return self._enter_priority_phase(Phase.END_STEP)
        if old == Phase.END_STEP:
            return self._enter_cleanup()
        if old == Phase.CLEANUP:
            return self._start_turn(Phase.CLEANUP.value, increment_turn=True)
        raise AssertionError(f"unsupported phase transition from {old.value}")
