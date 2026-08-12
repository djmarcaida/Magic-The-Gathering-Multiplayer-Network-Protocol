"""GUI-safe command API which translates user intent into MTGNP PDUs."""

from __future__ import annotations

from client.state_store import ClientStateStore


class ClientController:
    """
    Main orchestration layer for the client.

    Provides a high-level API for generating and sending valid MTGNP protocol
    messages. Automatically attaches the correct sequence number (priority token)
    required by the server for state-mutating actions.
    """
    def __init__(self, player_id: str, sender, store: ClientStateStore):
        self.player_id = player_id
        self.sender = sender
        self.store = store
        self._client_seq = 1

    def _send(self, pdu_type: str, *, token: int | None = None, **fields):
        seq = token if token is not None else self._client_seq
        if token is None:
            self._client_seq += 1
        pdu = {"type": pdu_type, "seq_num": seq, **fields}
        self.sender.send(pdu)
        return pdu

    def _action_token(self) -> int:
        return self.store.priority_token or self.store.last_server_seq or self._client_seq

    def ready(self, deck_list): return self._send("PLAYER_READY", player_id=self.player_id,
                                                  deck_list=list(deck_list))
    def mulligan(self): return self._send("MULLIGAN_CHOICE", token=self.store.last_server_seq,
                                          keep=False, cards_to_bottom=[])
    def keep(self, cards_to_bottom=()): return self._send("MULLIGAN_CHOICE",
                                                           token=self.store.last_server_seq,
                                                           keep=True,
                                                           cards_to_bottom=list(cards_to_bottom))
    def pass_priority(self): return self._send("PRIORITY_PASS", token=self.store.priority_token)
    def play_land(self, card_id): return self._send("PLAY_LAND", token=self._action_token(),
                                                    card_id=card_id)
    def cast_spell(self, card_id, targets=(), mana_payment=None, choices=None):
        return self._send("CAST_SPELL", token=self._action_token(), card_id=card_id,
                          targets=list(targets), mana_payment=dict(mana_payment or {}),
                          choices=dict(choices or {}))
    def activate_ability(self, source_id, ability_index, targets=(), cost_payment=None):
        return self._send("ACTIVATE_ABILITY", token=self._action_token(), source_id=source_id,
                          ability_index=int(ability_index), targets=list(targets),
                          cost_payment=dict(cost_payment or {}))
    def declare_attackers(self, attackers): return self._send("DECLARE_ATTACKERS",
                                                               token=self._action_token(),
                                                               attackers=list(attackers))
    def declare_blockers(self, blockers): return self._send("DECLARE_BLOCKERS",
                                                             token=self._action_token(),
                                                             blockers=dict(blockers))
    def assign_damage_order(self, attacker_id, blocker_order):
        return self._send("ASSIGN_DAMAGE_ORDER", token=self._action_token(),
                          attacker_id=attacker_id, blocker_order=list(blocker_order))
    def trigger_order(self, ordered_trigger_ids):
        return self._send("TRIGGER_ORDER_RESPONSE", token=self.store.last_server_seq,
                          ordered_trigger_ids=list(ordered_trigger_ids))
    def trigger_choice(self, trigger_id, accept, chosen_target=None):
        fields = {"trigger_id": trigger_id, "accept": bool(accept)}
        if chosen_target is not None: fields["chosen_target"] = chosen_target
        return self._send("TRIGGER_CHOICE_RESPONSE", token=self.store.last_server_seq, **fields)
    def discard(self, card_ids): return self._send("DISCARD", token=self._action_token(),
                                                    card_ids=list(card_ids))
    def concede(self): return self._send("CONCEDE", player_id=self.player_id)
    def ping(self, timestamp): return self._send("PING", timestamp=timestamp)
