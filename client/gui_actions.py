"""Validation and dispatch helpers shared by the Tkinter action controls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def parse_identifiers(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_mana(value: str) -> dict[str, int]:
    if not value.strip():
        return {}
    payment: dict[str, int] = {}
    try:
        for item in value.split(","):
            color, count = item.split("=", 1)
            key = color.strip().upper()
            if key == "GENERIC":
                key = "X"
            amount = int(count.strip())
            if key not in {"W", "U", "B", "R", "G", "C", "X"} or amount < 0:
                raise ValueError
            payment[key] = amount
    except ValueError as exc:
        raise ValueError("Mana must use COLOR=COUNT entries, for example R=1 or generic=2.") from exc
    return payment


def parse_blockers(value: str) -> dict[str, list[str]]:
    if not value.strip():
        return {}
    blockers: dict[str, list[str]] = {}
    try:
        for assignment in value.split(";"):
            attacker, defenders = assignment.split("=", 1)
            attacker = attacker.strip()
            blocker_ids = parse_identifiers(defenders)
            if not attacker or not blocker_ids:
                raise ValueError
            blockers[attacker] = blocker_ids
    except ValueError as exc:
        raise ValueError(
            "Blockers must use ATTACKER=BLOCKER entries; separate assignments with semicolons."
        ) from exc
    return blockers


def _one(selected: Sequence[str]) -> str:
    if len(selected) != 1:
        raise ValueError("Select one card before using this action.")
    return selected[0]


def dispatch_gui_action(controller, action: str, selected: Sequence[str] = (),
                        fields: Mapping[str, object] | None = None):
    fields = fields or {}
    if action == "keep":
        return controller.keep(selected)
    if action == "mulligan":
        return controller.mulligan()
    if action == "pass_priority":
        return controller.pass_priority()
    if action == "play_land":
        return controller.play_land(_one(selected))
    if action == "cast_spell":
        return controller.cast_spell(
            _one(selected),
            parse_identifiers(str(fields.get("targets", ""))),
            parse_mana(str(fields.get("mana", ""))),
        )
    if action == "activate_ability":
        return controller.activate_ability(
            _one(selected),
            int(fields.get("ability_index", 0)),
            parse_identifiers(str(fields.get("targets", ""))),
            parse_identifiers(str(fields.get("cost", ""))),
        )
    if action == "declare_attackers":
        return controller.declare_attackers(selected)
    if action == "declare_blockers":
        if "blockers" in fields:
            return controller.declare_blockers(
                {str(attacker): list(blockers)
                 for attacker, blockers in dict(fields["blockers"]).items()}
            )
        return controller.declare_blockers(parse_blockers(str(fields.get("assignments", ""))))
    if action == "assign_damage_order":
        if "order_ids" in fields:
            return controller.assign_damage_order(_one(selected), list(fields["order_ids"]))
        return controller.assign_damage_order(
            _one(selected), parse_identifiers(str(fields.get("order", "")))
        )
    if action == "trigger_order":
        return controller.trigger_order(parse_identifiers(str(fields.get("order", ""))))
    if action == "trigger_choice":
        target = str(fields.get("target", "")).strip() or None
        return controller.trigger_choice(
            str(fields.get("trigger_id", "")), bool(fields.get("accept", False)), target
        )
    if action == "discard":
        return controller.discard(selected)
    if action == "concede":
        return controller.concede()
    raise ValueError(f"Unknown GUI action: {action}")
