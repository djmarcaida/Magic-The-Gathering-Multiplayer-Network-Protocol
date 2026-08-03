"""Priority and LIFO stack mechanics independent of presentation/networking."""

from __future__ import annotations

from enum import Enum

from server.game_state import StackItem


class PriorityOutcome(str, Enum):
    TRANSFER = "TRANSFER"
    RESOLVE_TOP = "RESOLVE_TOP"
    ADVANCE_STEP = "ADVANCE_STEP"


class PriorityError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PriorityStack:
    def __init__(self, active_player: str, non_active_player: str,
                 stack: list[StackItem] | None = None):
        self.active_player = active_player
        self.non_active_player = non_active_player
        self.stack = stack if stack is not None else []
        self.holder: str | None = None
        self.token: int | None = None
        self.consecutive_passes = 0

    def open(self, player_id: str, token: int) -> None:
        self.consecutive_passes = 0
        self.grant(player_id, token)

    def grant(self, player_id: str, token: int) -> None:
        self.holder = player_id
        self.token = token

    def _validate(self, player_id: str, token: int) -> None:
        if token != self.token:
            raise PriorityError("STALE_ACTION", "action does not echo the current request token")
        if player_id != self.holder:
            raise PriorityError("NOT_YOUR_PRIORITY", "player does not hold priority")

    def act(self, player_id: str, token: int) -> None:
        self._validate(player_id, token)
        self.consecutive_passes = 0

    def pass_priority(self, player_id: str, token: int) -> PriorityOutcome:
        self._validate(player_id, token)
        self.consecutive_passes += 1
        if self.consecutive_passes == 1:
            return PriorityOutcome.TRANSFER
        self.consecutive_passes = 0
        self.holder = self.active_player
        return PriorityOutcome.RESOLVE_TOP if self.stack else PriorityOutcome.ADVANCE_STEP

    def push(self, item: StackItem) -> None:
        self.stack.append(item)
        self.consecutive_passes = 0

    def pop(self) -> StackItem:
        return self.stack.pop()
