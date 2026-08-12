# MTGNP 9-Minute Presentation Guide

This guide explains each grading criterion and tells you how to demonstrate it in the video.

## 1. TCP Server Setup & Client Accept

What to explain:
- The server is authoritative and accepts exactly two player connections.
- The server reserves seats for reconnecting players when their socket disconnects.

Code references:
- `server/main.py`
- `server/connection_manager.py`

Demonstration:
1. Run `python -m server.main --host 127.0.0.1 --port 4444`.
2. Start two GUI clients:
   - `python -m client.gui_main --host 127.0.0.1 --port 4444 --id player_1 --deck decks/red.json`
   - `python -m client.gui_main --host 127.0.0.1 --port 4444 --id player_2 --deck decks/blue.json`
3. Mention that opening a third client connection is rejected and only two seats are active.

## 2. Message Framing

What to explain:
- Every network message is framed as UTF-8 JSON with a 4-byte unsigned big-endian length prefix.
- Payloads are capped at 65,535 bytes.

Code references:
- `common/framing.py`

Demonstration:
- Show `encode_pdu` and `recv_pdu`.
- Point out `struct.pack("!I", len(payload))` and JSON serialization/deserialization.

## 3. PDU Structure & seq_num

What to explain:
- Every PDU includes `type` and `seq_num`.
- `common/pdus.py` defines all supported PDU names, directions, required fields, and accepted error codes.
- The server assigns `seq_num` for outgoing PDUs and uses it as request tokens.
- The client echoes the current token in its action PDUs.

Code references:
- `common/pdus.py`
- `server/game_engine.py` (`GameEngine._pdu`, `GameEngine._require_token`)
- `client/controller.py`

Demonstration:
- Explain `PDU_DIRECTIONS`, `REQUIRED_FIELDS`, and validation rules.
- Show the server sequence generation and client token usage.

## 4. LOBBY & PLAYER_READY Handling

What to explain:
- Players join by sending `PLAYER_READY`.
- The server validates the deck and player ID.
- The game waits in lobby state until two valid players are ready.

Code references:
- `server/game_engine.py` (`_handle_ready`)
- `common/cards.py` (`CardCatalog.validate_deck`)

Demonstration:
- Show clients submitting ready messages.
- Explain the `LOBBY` state and how the server moves to game setup once both players are registered.
- Mention duplicate IDs, invalid deck IDs, and deck size checks.

## 5. GAME_SETUP & MULLIGAN

What to explain:
- After two players are ready, the server shuffles decks and deals opening hands.
- The game enters `MULLIGAN` lifecycle.
- Each player chooses either `keep` or `mulligan`.

Code references:
- `server/game_state.py` (`GameState.new`)
- `server/game_engine.py` (`_handle_mulligan`, `_start_turn`)
- `README.md` for rules summary

Demonstration:
- Show the first `GAME_STATE_UPDATE` with `lifecycle: MULLIGAN`.
- Demonstrate a mulligan reroll or a keep with bottomed cards.
- Note that the first player still skips the first turn draw as required.

## 6. IN_GAME Phase & Step Transitions

What to explain:
- The engine drives a full phase cycle from `UNTAP` through `CLEANUP`.
- `PHASE_TRANSITION` messages notify clients about phase changes.
- Priority windows open after phase transitions.

Code references:
- `server/game_engine.py` (`advance_step`, `_enter_priority_phase`, `_transition`)
- `server/game_state.py` (`Phase` enum)

Demonstration:
- Show the GUI phase strip updating live.
- Mention the phase progression: `PRECOMBAT_MAIN`, `BEGIN_COMBAT`, `DECLARE_ATTACKERS`, `DECLARE_BLOCKERS`, `ASSIGN_DAMAGE_ORDER`, `FIRST_STRIKE_DAMAGE`, `COMBAT_DAMAGE`, `END_OF_COMBAT`, `POSTCOMBAT_MAIN`, `END_STEP`, `CLEANUP`.

## 7. GAME_OVER & Session Restart

What to explain:
- The game can end for `LIFE_ZERO`, `DECK_EMPTY`, `CONCEDE`, or `DISCONNECT`.
- The server broadcasts `GAME_OVER`, resets game state, and allows fresh `PLAYER_READY` for a restart.

Code references:
- `server/game_engine.py` (`_finish`, `connection_lost`, `_resolve_top`)
- `server/main.py` reconnect logic

Demonstration:
- Cause a game over by conceding or killing a player.
- Show the `GAME_OVER` PDU and explain the transition back to lobby/restart.

## 8. Game State Management & Hidden Info

What to explain:
- The server owns authoritative game state.
- Clients receive only allowed data.
- Opponent hand contents are hidden; only counts are sent.
- Library order is hidden; only counts are sent.

Code references:
- `server/game_state.py` (`GameState.visible_to`)
- `client/state_store.py`

Demonstration:
- Point out that the GUI shows only your hand contents and opponent hand count.
- Show library and graveyard counts.
- Emphasize that outcome logic never runs on the client.

## 9. Priority & Stack Resolution

What to explain:
- Priority is managed by `PriorityStack` on the server.
- One pass transfers priority; the second pass resolves the stack or advances the step.
- Spells and triggers are placed on a LIFO stack.
- `PRIORITY_GRANT`, `PRIORITY_PASS`, `STACK_PUSH`, and `STACK_RESOLVE` are the core PDUs.

Code references:
- `server/priority_stack.py`
- `server/game_engine.py` (`_grant_priority`, `_handle_priority_pass`, `_handle_cast_spell`, `_resolve_top`)
- `client/state_store.py`

Demonstration:
- Cast a spell and show the stack push event.
- Pass priority and show how the stack resolves.
- Explain that the server enforces the rules and only advances once both players pass.

## 10. Combat System

What to explain:
- Attackers are declared during `DECLARE_ATTACKERS`.
- Defenders assign blockers during `DECLARE_BLOCKERS`.
- Multiple blockers may be assigned to one attacker.
- The server handles damage ordering, first strike, double strike, and simultaneous damage.
- There is no trample carry-over in this baseline.

Code references:
- `server/game_engine.py` (`_handle_attackers`, `_handle_blockers`, `_handle_damage_order`, `resolve_combat_damage`, `_enter_combat_damage`)
- `server/game_state.py` (`CombatState`, `PermanentState`)

Demonstration:
- Declare attackers.
- Declare blockers with one attacker blocked by multiple creatures.
- Submit `ASSIGN_DAMAGE_ORDER` and show the resulting combat damage events.
- Point out life totals and creatures dying from damage.

## 11. Client Sending & State Rendering

What to explain:
- The client uses `ClientController` to send PDUs.
- `ClientNetwork` handles framed TCP transport.
- `ClientStateStore` applies server updates.
- The GUI renders authoritative state without making game decisions locally.

Code references:
- `client/controller.py`
- `client/network_client.py`
- `client/state_store.py`
- `client/gui.py`

Demonstration:
- Use the GUI to click a card and cast/play it.
- Show the GUI refreshing after the server sends `GAME_STATE_UPDATE`.
- Highlight the phase strip, hand scrolling, battlefield rows, stack display, and resource panel.

## 12. PING/PONG Heartbeat

What to explain:
- The client optionally sends periodic `PING` messages.
- The server responds with `PONG` using the same `seq_num` and timestamp.
- The client watches `last_pong` and can detect a failed heartbeat.

Code references:
- `client/network_client.py`
- `server/game_engine.py` (`process` handles `PING`)

Demonstration:
- Describe the heartbeat thread in `ClientNetwork`.
- Explain that `PONG` keeps the connection alive and detects stale connection.

## 13. Error PDU Handling

What to explain:
- Invalid or illegal actions result in `ERROR` PDUs.
- Each error includes `code`, `message`, and the rejected action.
- The client logs or displays the error without applying illegal changes.

Code references:
- `common/pdus.py`
- `server/game_engine.py` (`_error`, `process`)
- `client/state_store.py`

Demonstration:
- Try an illegal action, such as playing a land in the wrong phase or casting without enough mana.
- Show the returned `ERROR` PDU and confirm the state remains valid.

## 14. Readability & Comments

What to explain:
- The code is layered and separated by responsibility:
  - transport (`common/framing.py`, `client/network_client.py`)
  - protocol validation (`common/pdus.py`)
  - authoritative game rules (`server/game_engine.py`)
  - state projection and rendering (`client/state_store.py`, `client/gui.py`)
- The repository includes docstrings and an explanatory `README.md`.

Files to cite:
- `README.md`
- `common/framing.py`
- `server/game_engine.py`
- `client/controller.py`
- `client/gui.py`

Demonstration:
- Briefly show the project structure.
- Mention that game logic is not mixed with presentation.

## 15. Full Card Effects

What to explain:
- The five required effects are implemented:
  - `Lightning Bolt`
  - `Counterspell`
  - `Unsummon`
  - `Giant Growth`
  - `Gray Merchant of Asphodel`
- Lands produce mana and permanents enter play with correct stats.

Code references:
- `common/cards.py`
- `server/game_engine.py` (`_resolve_top`, `_validate_spell_targets`)
- `README.md` effect summary

Demonstration:
- Cast `Lightning Bolt` or `Giant Growth`.
- Use `Counterspell` to counter a spell on the stack.
- Show `Gray Merchant` trigger resolving when it enters the battlefield.

## 16. Bonus Features

What to explain:
- The GUI includes card artwork, rounded-card previews, hover/enlarge behavior, mouse-wheel hand scrolling, and keyboard navigation.
- The terminal client shares the same transport, state store, and controller as the GUI.
- Reconnection is handled by re-sending `PLAYER_READY` and using a reconnect timeout.

Files to cite:
- `client/gui.py`
- `client/ui.py`
- `scripts/demo_game.py`
- `README.md`

Demonstration:
- Show GUI hand scrolling and card highlighting.
- Mention the terminal command set from `README.md`.
- Explain that both GUI and terminal use the same backend protocol and state handling.

## Presentation Order Recommendation

1. Start with server setup and lobby flow.
2. Explain framing and PDU validation.
3. Show `PLAYER_READY`, lobby state, and game setup.
4. Demonstrate mulligans and phase transitions.
5. Show priority/stack behavior with a spell cast.
6. Demonstrate combat and damage resolution.
7. Trigger a game over and restart.
8. Mention heartbeat and error handling.
9. Wrap up with card effects and GUI/terminal separation.

Keep the video focused on the features, and use these code references to back each claim with the implementation.