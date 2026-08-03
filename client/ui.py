"""Terminal-only presentation adapter; contains no socket or rule logic."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    args: tuple[str, ...] = ()


COMMANDS = {"ready", "keep", "mulligan", "land", "cast", "activate", "pass",
            "attack", "block", "damage-order", "trigger-order", "trigger-choice",
            "discard", "concede", "state", "help", "quit"}


def parse_command(line: str) -> Command:
    parts = shlex.split(line)
    if not parts:
        raise ValueError("enter a command; use 'help' for choices")
    name = parts[0].lower()
    if name not in COMMANDS:
        raise ValueError(f"unknown command {name!r}; use 'help'")
    return Command(name, tuple(parts[1:]))


def _mana(parts: tuple[str, ...]) -> dict[str, int]:
    try:
        return {key.upper(): int(value) for key, value in (part.split("=", 1) for part in parts)}
    except (ValueError, TypeError) as exc:
        raise ValueError("mana must use COLOR=COUNT entries, for example R=1 or X=2") from exc


class TerminalUI:
    def __init__(self, controller, store, *, input_fn=input, output_fn=print):
        self.controller = controller
        self.store = store
        self.input = input_fn
        self.output = output_fn
        store.subscribe_state(self.render_state)
        store.subscribe_event(lambda pdu: self.output(f"EVENT {pdu['type']}: {json.dumps(pdu)}"))
        store.subscribe_error(lambda pdu: self.output(f"ERROR {pdu['code']}: {pdu['message']}"))

    def render_state(self, state):
        self.output(json.dumps(state, indent=2, sort_keys=True))

    def run(self):
        self.output("MTGNP client ready. Type 'help'.")
        while True:
            try:
                command = parse_command(self.input("mtgnp> "))
                if command.name == "quit": return
                self.execute(command)
            except (ValueError, IndexError) as exc:
                self.output(f"Invalid command: {exc}")

    def execute(self, command: Command):
        a = command.args
        c = self.controller
        if command.name == "help":
            self.output("Commands: " + ", ".join(sorted(COMMANDS)))
        elif command.name == "state": self.render_state(self.store.state)
        elif command.name == "ready": c.ready(a)
        elif command.name == "keep": c.keep(a)
        elif command.name == "mulligan": c.mulligan()
        elif command.name == "land": c.play_land(a[0])
        elif command.name == "cast": c.cast_spell(a[0], [] if a[1] == "-" else a[1:2], _mana(a[2:]))
        elif command.name == "activate": c.activate_ability(a[0], int(a[1]), a[2:3], a[3:])
        elif command.name == "pass": c.pass_priority()
        elif command.name == "attack": c.declare_attackers(a)
        elif command.name == "block": c.declare_blockers({a[0]: list(a[1:])})
        elif command.name == "damage-order": c.assign_damage_order(a[0], a[1:])
        elif command.name == "trigger-order": c.trigger_order(a)
        elif command.name == "trigger-choice": c.trigger_choice(a[0], a[1].lower() in {"yes", "true", "1"}, a[2] if len(a) > 2 else None)
        elif command.name == "discard": c.discard(a)
        elif command.name == "concede": c.concede()
