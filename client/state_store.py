"""Presentation-neutral client-side projection of authoritative server state."""

from __future__ import annotations

from collections.abc import Callable


REQUEST_TOKEN_TYPES = {"GAME_STATE_UPDATE", "TRIGGER_ORDER", "TRIGGER_CHOICE"}


class ClientStateStore:
    def __init__(self):
        self.state: dict[str, object] = {}
        self.priority_token: int | None = None
        self.last_server_seq: int | None = None
        self._state_subscribers: list[Callable[[dict[str, object]], None]] = []
        self._event_subscribers: list[Callable[[dict[str, object]], None]] = []
        self._error_subscribers: list[Callable[[dict[str, object]], None]] = []

    def subscribe_state(self, callback): self._state_subscribers.append(callback)
    def subscribe_event(self, callback): self._event_subscribers.append(callback)
    def subscribe_error(self, callback): self._error_subscribers.append(callback)

    def apply_pdu(self, pdu: dict[str, object]) -> None:
        pdu_type = pdu.get("type")
        seq = pdu.get("seq_num")
        if isinstance(seq, int) and pdu_type in REQUEST_TOKEN_TYPES:
            self.last_server_seq = seq
        if pdu_type == "GAME_STATE_UPDATE":
            self.state = dict(pdu["state"])
            token = self.state.get("priority_token")
            self.priority_token = token if isinstance(token, int) else None
            for callback in tuple(self._state_subscribers):
                callback(dict(self.state))
        elif pdu_type == "ERROR":
            for callback in tuple(self._error_subscribers):
                callback(dict(pdu))
        else:
            if pdu_type == "PRIORITY_GRANT":
                self.priority_token = pdu["seq_num"]
                self.state["priority_holder"] = pdu["player_id"]
                self.state["priority_token"] = pdu["seq_num"]
                for callback in tuple(self._state_subscribers):
                    callback(dict(self.state))
            for callback in tuple(self._event_subscribers):
                callback(dict(pdu))
