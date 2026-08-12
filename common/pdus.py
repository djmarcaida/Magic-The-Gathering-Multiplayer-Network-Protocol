"""MTGNP v1.0 PDU registry and structural validation."""

from __future__ import annotations

from collections.abc import Mapping

PDU_DIRECTIONS = {
    "PLAYER_READY": "C->S", "GAME_STATE_UPDATE": "S->C",
    "MULLIGAN_CHOICE": "C->S", "PHASE_TRANSITION": "S->ALL",
    "PRIORITY_GRANT": "S->C", "PRIORITY_PASS": "C->S",
    "CAST_SPELL": "C->S", "ACTIVATE_ABILITY": "C->S",
    "STACK_PUSH": "S->ALL", "TRIGGER_ORDER": "S->C",
    "TRIGGER_ORDER_RESPONSE": "C->S", "TRIGGER_CHOICE": "S->C",
    "TRIGGER_CHOICE_RESPONSE": "C->S", "STACK_RESOLVE": "S->ALL",
    "DECLARE_ATTACKERS": "C->S", "DECLARE_BLOCKERS": "C->S",
    "ASSIGN_DAMAGE_ORDER": "C->S", "COMBAT_DAMAGE_RESULT": "S->ALL",
    "PLAY_LAND": "C->S", "DISCARD": "C->S", "CONCEDE": "C->S",
    "GAME_OVER": "S->ALL", "ERROR": "S->C", "PING": "C->S", "PONG": "S->C",
}

REQUIRED_FIELDS = {
    "PLAYER_READY": ("player_id", "deck_list"),
    "GAME_STATE_UPDATE": ("state",),
    "MULLIGAN_CHOICE": ("keep", "cards_to_bottom"),
    "PHASE_TRANSITION": ("from_phase", "to_phase", "active_player", "turn"),
    "PRIORITY_GRANT": ("player_id", "time_limit_ms"),
    "PRIORITY_PASS": (),
    "CAST_SPELL": ("card_id", "targets", "mana_payment"),
    "ACTIVATE_ABILITY": ("source_id", "ability_index", "targets", "cost_payment"),
    "STACK_PUSH": ("stack_item_id", "item_type", "source", "targets", "controller"),
    "TRIGGER_ORDER": ("player_id", "trigger_ids"),
    "TRIGGER_ORDER_RESPONSE": ("ordered_trigger_ids",),
    "TRIGGER_CHOICE": ("trigger_id", "source_id", "effect_summary", "legal_targets", "requires_target"),
    "TRIGGER_CHOICE_RESPONSE": ("trigger_id", "accept"),
    "STACK_RESOLVE": ("stack_item_id", "result", "state_changes"),
    "DECLARE_ATTACKERS": ("attackers",),
    "DECLARE_BLOCKERS": ("blockers",),
    "ASSIGN_DAMAGE_ORDER": ("attacker_id", "blocker_order"),
    "COMBAT_DAMAGE_RESULT": ("damage_events", "life_totals", "creatures_died"),
    "PLAY_LAND": ("card_id",),
    "DISCARD": ("card_ids",),
    "CONCEDE": ("player_id",),
    "GAME_OVER": ("winner_id", "loser_id", "reason"),
    "ERROR": ("code", "message", "rejected_action"),
    "PING": ("timestamp",), "PONG": ("timestamp",),
}

PDU_TYPES = frozenset(PDU_DIRECTIONS)
CLIENT_TO_SERVER_TYPES = frozenset(k for k, v in PDU_DIRECTIONS.items() if v == "C->S")
SERVER_TO_CLIENT_TYPES = frozenset(k for k, v in PDU_DIRECTIONS.items() if v in {"S->C", "S->ALL"})
ERROR_CODES = frozenset({
    "INVALID_JSON", "ILLEGAL_DECK", "UNKNOWN_TYPE", "STALE_ACTION",
    "NOT_YOUR_PRIORITY", "ILLEGAL_ACTION", "ILLEGAL_TARGET",
    "TRIGGER_ORDER_INVALID", "TRIGGER_CHOICE_INVALID", "INSUFFICIENT_MANA",
    "WRONG_PHASE", "DUPLICATE_ID",
})


class PDUValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_pdu(pdu: Mapping[str, object], *, direction: str | None = None) -> dict[str, object]:
    """
    Validate the structural integrity and directionality of a parsed PDU.

    Ensures the PDU type is registered, all required fields are present, and the
    sequence number is a valid integer. Raises PDUValidationError if any checks fail.
    """
    if not isinstance(pdu, Mapping):
        raise PDUValidationError("INVALID_JSON", "PDU must be an object")
    pdu_type = pdu.get("type")
    if not isinstance(pdu_type, str) or pdu_type not in PDU_TYPES:
        raise PDUValidationError("UNKNOWN_TYPE", f"Unknown PDU type: {pdu_type!r}")
    if direction is not None:
        allowed = CLIENT_TO_SERVER_TYPES if direction == "C->S" else SERVER_TO_CLIENT_TYPES
        if pdu_type not in allowed:
            raise PDUValidationError("UNKNOWN_TYPE", f"{pdu_type} is not valid for {direction}")
    seq_num = pdu.get("seq_num")
    if isinstance(seq_num, bool) or not isinstance(seq_num, int) or seq_num < 0:
        raise PDUValidationError("ILLEGAL_ACTION", "seq_num must be a non-negative integer")
    missing = [name for name in REQUIRED_FIELDS[pdu_type] if name not in pdu]
    if missing:
        raise PDUValidationError("ILLEGAL_ACTION", f"Missing required field(s): {', '.join(missing)}")
    return dict(pdu)
