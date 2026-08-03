"""Immutable card catalog loaded from the supplied MTGNP master list."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


class DeckValidationError(ValueError):
    """The submitted deck cannot be built from supplied card instances."""


@dataclass(frozen=True)
class CardDefinition:
    base_id: str
    name: str
    card_type: str
    subtype: str
    colors: tuple[str, ...]
    mana_cost: Mapping[str, int]
    power: int | None
    toughness: int | None
    copies: int
    keywords: tuple[str, ...]
    effect: str


@dataclass(frozen=True)
class CardInstance:
    card_id: str
    copy_number: int
    definition: CardDefinition

    def __getattr__(self, name: str):
        return getattr(self.definition, name)


class CardCatalog:
    def __init__(self, definitions: Mapping[str, CardDefinition],
                 instances: Mapping[str, CardInstance]):
        self.definitions = MappingProxyType(dict(definitions))
        self.instances = MappingProxyType(dict(instances))

    @classmethod
    def from_json(cls, path: str | Path) -> "CardCatalog":
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("card catalog root must be a list")
        definitions: dict[str, CardDefinition] = {}
        instances: dict[str, CardInstance] = {}
        for row in rows:
            definition = CardDefinition(
                base_id=row["base_id"], name=row["name"], card_type=row["card_type"],
                subtype=row.get("subtype", ""), colors=tuple(row.get("colors", ())),
                mana_cost=MappingProxyType(dict(row.get("mana_cost", {}))),
                power=row.get("power"), toughness=row.get("toughness"),
                copies=row["copies"], keywords=tuple(row.get("keywords", ())),
                effect=row.get("effect", ""),
            )
            if definition.base_id in definitions or definition.copies < 1:
                raise ValueError(f"invalid duplicate/copy count for {definition.base_id}")
            definitions[definition.base_id] = definition
            for copy_number in range(1, definition.copies + 1):
                card_id = f"{definition.base_id}_{copy_number:03d}"
                instances[card_id] = CardInstance(card_id, copy_number, definition)
        return cls(definitions, instances)

    def contains(self, card_id: str) -> bool:
        return card_id in self.instances

    def get(self, card_id: str) -> CardInstance:
        try:
            return self.instances[card_id]
        except KeyError as exc:
            raise KeyError(f"unknown supplied card instance: {card_id}") from exc

    def validate_deck(self, card_ids: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if not 1 <= len(card_ids) <= 50:
            raise DeckValidationError("deck must contain 1 to 50 cards")
        if len(set(card_ids)) != len(card_ids):
            raise DeckValidationError("deck contains duplicate instance IDs")
        unknown = [card_id for card_id in card_ids if card_id not in self.instances]
        if unknown:
            raise DeckValidationError(f"deck contains unknown card IDs: {', '.join(unknown)}")
        return tuple(card_ids)
