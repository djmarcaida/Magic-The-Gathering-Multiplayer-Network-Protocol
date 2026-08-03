# MTGNP Required Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the required MTGNP v1.0 server and two GUI-ready terminal clients using only the supplied RFC, card list, and planning PDF.

**Architecture:** Socket-reader threads turn framed client PDUs into seat-tagged queue events. A single server game loop owns and mutates all authoritative game state, then emits event PDUs and personalized snapshots. Each client separates TCP transport, controller commands, state storage, and presentation so a future GUI can replace the CLI.

**Tech Stack:** Python 3.12 standard library (`socket`, `threading`, `queue`, `json`, `dataclasses`, `enum`, `argparse`, `unittest`); no production dependencies.

## Global Constraints

- Game behavior and card data come only from `CSNETWK_MP_MTGNP.pdf`, `mtgnp_master_card_list.pdf`, `Prompt.pdf`, and the approved design specification.
- Implement the required 100-point baseline only; exclude GUI, spectator, complete-card-effect, and other bonus work.
- Preserve exact RFC PDU names and formal Section 10 field names.
- All state mutation occurs in the server game-loop thread.
- Clients render server state and never calculate legality or outcomes.
- Use test-driven development: add one failing behavior test, observe the intended failure, implement the minimum behavior, and rerun the narrow and full suites.
- Do not commit this plan. Do not commit implementation changes without separate user authorization.
- Keep `graphify-out/` and `tmp/` out of every staged or reviewed implementation file list.

---

## File Structure

### Shared protocol and data

- `common/__init__.py`: package marker.
- `common/framing.py`: exact-byte TCP framing, JSON encoding/decoding, payload limit, and verbose logging.
- `common/pdus.py`: 25 PDU names, directions, required fields, constructors, and validation.
- `common/cards.py`: immutable catalog loader, card-instance lookup, and legal-deck validation.
- `cards.json`: 58 supplied base cards plus enough copy metadata to derive all 312 supplied instance IDs.

### Server

- `server/__init__.py`: package marker.
- `server/game_state.py`: player, permanent, stack, combat, lifecycle, and personalized-state dataclasses.
- `server/priority_stack.py`: priority ownership, request tokens, passes, stack operations, trigger decisions, and resolution result types.
- `server/game_engine.py`: authoritative lifecycle, turns, actions, effects, state-based actions, combat, and outbound PDU descriptions.
- `server/connection_manager.py`: two-seat listener, socket-reader threads, queue events, serialized writes, heartbeat state, and reconnect grace period.
- `server/main.py`: arguments, wiring, game-loop process, signal/keyboard shutdown, and verbose mode.

### Client

- `client/__init__.py`: package marker.
- `client/network_client.py`: socket connection, framing, receive thread, heartbeat, and PDU callbacks.
- `client/state_store.py`: authoritative visible-state replacement and state/event/error subscriptions.
- `client/controller.py`: presentation-neutral player command API and request-token selection.
- `client/ui.py`: terminal renderer and command parser only.
- `client/main.py`: arguments and composition root.

### Tests and documentation

- `tests/__init__.py`: package marker.
- `tests/helpers.py`: socket pairs, deterministic decks, fake sender, and PDU assertion helpers.
- `tests/test_framing.py`: framing and verbose logging.
- `tests/test_pdus.py`: all PDU validators and error mapping.
- `tests/test_cards.py`: catalog totals, IDs, costs, effects, and deck validation.
- `tests/test_game_state.py`: state initialization and hidden-information views.
- `tests/test_lifecycle.py`: lobby, setup, mulligan, game over, and restart.
- `tests/test_priority_stack.py`: tokens, passes, stack, triggers, and fizzles.
- `tests/test_turn_combat.py`: phases, mana, cleanup, combat, and state-based actions.
- `tests/test_card_effects.py`: the five required effects.
- `tests/test_connection_manager.py`: two seats, refusal, heartbeat, and reconnect.
- `tests/test_client.py`: transport-independent controller/store/CLI contract.
- `tests/test_end_to_end.py`: real loopback server plus two scripted clients.
- `scripts/demo_game.py`: deterministic two-client demonstration using public client APIs.
- `README.md`: run, protocol, CLI, testing, work matrix, AI disclosure, and deviations.
- `README.pdf`: visually verified rendered deliverable.

---

### Task 1: Framing and PDU Contracts

**Files:**
- Create: `common/__init__.py`
- Modify: `common/framing.py`
- Modify: `common/pdus.py`
- Create: `tests/__init__.py`
- Create: `tests/test_framing.py`
- Create: `tests/test_pdus.py`

**Interfaces:**
- Produces `MAX_PDU_BYTES: int = 65535`.
- Produces `FramingError(code: str, message: str)`.
- Produces `encode_pdu(pdu: Mapping[str, object]) -> bytes`.
- Produces `recv_exact(sock: socket.socket, count: int) -> bytes`.
- Produces `send_pdu(sock, pdu, *, verbose=False, label="SEND", logger=print) -> None`.
- Produces `recv_pdu(sock, *, verbose=False, label="RECV", logger=print) -> dict[str, object]`.
- Produces `PDU_TYPES: frozenset[str]`, `CLIENT_TO_SERVER_TYPES`, and `SERVER_TO_CLIENT_TYPES`.
- Produces `PDUValidationError(code: str, message: str)` and `validate_pdu(pdu, *, direction=None) -> dict`.

The registry uses these exact contracts; fields listed after `seq_num` are the
required message-specific fields:

```python
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
    "GAME_OVER": "S->ALL", "ERROR": "S->C", "PING": "C->S",
    "PONG": "S->C",
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
    "TRIGGER_CHOICE": ("trigger_id", "source_id", "effect_summary",
                       "legal_targets", "requires_target"),
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
    "PING": ("timestamp",),
    "PONG": ("timestamp",),
}

ERROR_CODES = frozenset({
    "INVALID_JSON", "ILLEGAL_DECK", "UNKNOWN_TYPE", "STALE_ACTION",
    "NOT_YOUR_PRIORITY", "ILLEGAL_ACTION", "ILLEGAL_TARGET",
    "TRIGGER_ORDER_INVALID", "TRIGGER_CHOICE_INVALID",
    "INSUFFICIENT_MANA", "WRONG_PHASE", "DUPLICATE_ID",
})
```

- [ ] **Step 1: Add failing framing tests**

```python
class FramingTests(unittest.TestCase):
    def test_encode_pdu_prefixes_utf8_json_length(self):
        frame = encode_pdu({"type": "PING", "seq_num": 7, "timestamp": 12.5})
        size = struct.unpack("!I", frame[:4])[0]
        self.assertEqual(size, len(frame[4:]))

    def test_recv_pdu_reassembles_fragmented_socket_reads(self):
        left, right = socket.socketpair()
        frame = encode_pdu({"type": "PING", "seq_num": 1, "timestamp": 1.0})
        for chunk in (frame[:2], frame[2:5], frame[5:]):
            left.sendall(chunk)
        self.assertEqual(recv_pdu(right)["type"], "PING")
```

- [ ] **Step 2: Run framing tests and confirm missing imports/API failures**

Run: `python -m unittest tests.test_framing -v`

Expected: import or attribute failures for the framing API.

- [ ] **Step 3: Implement framing and verbose logging**

Use `struct.pack("!I", len(payload))`, compact deterministic JSON, an exact-read loop, the 65,535-byte guard, UTF-8/JSON error conversion, and one logger call containing the label plus readable JSON for every successful send/receive.

- [ ] **Step 4: Run framing tests to green**

Run: `python -m unittest tests.test_framing -v`

Expected: all framing tests pass with no warnings.

- [ ] **Step 5: Add failing PDU contract tests**

```python
class PDUContractTests(unittest.TestCase):
    def test_registry_contains_exactly_the_25_rfc_types(self):
        self.assertEqual(PDU_TYPES, EXPECTED_PDU_TYPES)

    def test_every_pdu_requires_type_and_integer_seq_num(self):
        with self.assertRaisesRegex(PDUValidationError, "seq_num"):
            validate_pdu({"type": "PRIORITY_PASS"}, direction="C->S")

    def test_direction_mismatch_is_unknown_type(self):
        with self.assertRaises(PDUValidationError) as raised:
            validate_pdu({"type": "GAME_OVER", "seq_num": 2}, direction="C->S")
        self.assertEqual(raised.exception.code, "UNKNOWN_TYPE")
```

- [ ] **Step 6: Run PDU tests and confirm registry/validation failures**

Run: `python -m unittest tests.test_pdus -v`

- [ ] **Step 7: Implement all 25 schemas and error codes**

Define exact required fields from RFC Section 10, reject booleans where an integer is required, keep optional fields explicit, and return a copied dictionary so validation never mutates caller input.

- [ ] **Step 8: Run Task 1 and full tests**

Run: `python -m unittest tests.test_framing tests.test_pdus -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 9: Review the Task 1 diff without committing**

Run: `git diff --check -- common tests`

---

### Task 2: Supplied Card Catalog and Authoritative State

**Files:**
- Modify: `cards.json`
- Create: `common/cards.py`
- Modify: `server/game_state.py`
- Create: `server/__init__.py`
- Create: `tests/helpers.py`
- Create: `tests/test_cards.py`
- Create: `tests/test_game_state.py`

**Interfaces:**
- Produces frozen `CardDefinition` and `CardInstance` dataclasses.
- Produces `CardCatalog.from_json(path)`, `get(card_id)`, `contains(card_id)`, and `validate_deck(card_ids)`.
- Produces `Lifecycle`, `Phase`, `PlayerState`, `PermanentState`, `StackItem`, `CombatState`, and `GameState`.
- Produces `GameState.new(players, decks, first_player, rng) -> GameState`.
- Produces `GameState.visible_to(player_id) -> dict[str, object]`.
- Produces test helpers `RED_DECK`, `BLUE_DECK`, `ready`, `make_engine`,
  `make_started_state`, `RecordingSender`, and `store_with_token` for later tests.

- [ ] **Step 1: Add failing catalog-total and known-card tests**

```python
class CardCatalogTests(unittest.TestCase):
    def test_catalog_matches_supplied_totals(self):
        self.assertEqual(len(self.catalog.definitions), 58)
        self.assertEqual(len(self.catalog.instances), 312)

    def test_lightning_bolt_uses_supplied_card_values(self):
        bolt = self.catalog.get("lightning_bolt_001")
        self.assertEqual((bolt.card_type, bolt.colors, bolt.mana_cost),
                         ("Instant", ("R",), {"R": 1}))
```

- [ ] **Step 2: Run catalog tests and confirm empty-catalog failures**

Run: `python -m unittest tests.test_cards -v`

- [ ] **Step 3: Populate `cards.json` from the supplied card list and implement loader validation**

Represent every supplied base row with its base ID, name, type, subtype, color, mana columns, power, toughness, copy count, keywords, and simplified effect. Derive instance IDs as `<base_id>_<three-digit copy>` and assert the per-color and total counts from page 18.

- [ ] **Step 4: Run catalog tests to green**

Run: `python -m unittest tests.test_cards -v`

- [ ] **Step 5: Add failing state and privacy tests**

```python
class GameStateTests(unittest.TestCase):
    def test_new_game_sets_20_life_and_personalizes_hands(self):
        state = make_started_state()
        p1_view = state.visible_to("player_1")
        self.assertEqual(p1_view["life_totals"]["player_1"], 20)
        self.assertIn("player_1", p1_view["hand"])
        self.assertNotIn("player_2", p1_view["hand"])
        self.assertEqual(p1_view["hand_counts"]["player_2"], 7)
```

- [ ] **Step 6: Run state tests and confirm missing model failures**

Run: `python -m unittest tests.test_game_state -v`

- [ ] **Step 7: Implement focused state dataclasses and snapshot filtering**

Keep library order and both hands server-only. Serialize only the receiving hand, opponent hand count, public zones, public stack, life, phase, active player, priority holder, and turn data.

- [ ] **Step 8: Run Task 2 and full tests**

Run: `python -m unittest tests.test_cards tests.test_game_state -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 9: Review the Task 2 diff without committing**

Run: `git diff --check -- cards.json common server tests`

---

### Task 3: Lifecycle, Mulligan, Errors, and Restart

**Files:**
- Modify: `server/game_engine.py`
- Modify: `server/game_state.py`
- Create: `tests/test_lifecycle.py`

**Interfaces:**
- Produces `Outbound(recipient: str | None, pdu: dict)`.
- Produces `GameEngine(catalog, rng, priority_timeout_ms=60000)`.
- Produces `GameEngine.process(seat_id, pdu) -> list[Outbound]`.
- Produces `GameEngine.connection_lost(seat_id)` and `reconnect(seat_id, player_id)`.
- Produces `GameEngine.snapshot_updates() -> list[Outbound]`.

- [ ] **Step 1: Add failing lobby/setup tests**

```python
def test_two_valid_ready_pdus_start_personalized_mulligan(self):
    engine = make_engine()
    engine.process("seat_1", ready("player_1", RED_DECK))
    outgoing = engine.process("seat_2", ready("player_2", BLUE_DECK))
    updates = [m for m in outgoing if m.pdu["type"] == "GAME_STATE_UPDATE"]
    self.assertEqual(engine.state.lifecycle, Lifecycle.MULLIGAN)
    self.assertEqual({m.recipient for m in updates}, {"seat_1", "seat_2"})
```

- [ ] **Step 2: Run lifecycle tests and confirm missing-engine failures**

Run: `python -m unittest tests.test_lifecycle -v`

- [ ] **Step 3: Implement lobby validation and automatic setup**

Cover non-empty unique IDs, 1-50 legal unique instance IDs, replacement ready submissions, life 20, server shuffle, up-to-seven opening hands, random first player, and personalized Mulligan updates.

- [ ] **Step 4: Add failing repeated-mulligan tests**

Test redraw, request-token echo, exact bottom count, invalid card rejection, short-deck cap, and transition only after both players keep.

- [ ] **Step 5: Implement London mulligans and transition to turn one**

Start turn at one, use `MULLIGAN -> UNTAP`, and never draw for the first player on turn one.

- [ ] **Step 6: Add failing game-over/restart/error tests**

Test `LIFE_ZERO`, `DECK_EMPTY`, `CONCEDE`, and `DISCONNECT`; NAP wins simultaneous life zero; `GAME_OVER` returns to lobby on retained sockets; invalid actions preserve state and return the correct error/retry token.

- [ ] **Step 7: Implement game-over, lobby reset, and recoverable errors**

Reset lobby IDs/decks only after sending `GAME_OVER`; preserve connection seats and server sequence continuity.

- [ ] **Step 8: Run Task 3 and full tests**

Run: `python -m unittest tests.test_lifecycle -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 9: Review the Task 3 diff without committing**

Run: `git diff --check -- server tests`

---

### Task 4: Priority, Stack, Triggers, and Five Effects

**Files:**
- Modify: `server/priority_stack.py`
- Modify: `server/game_engine.py`
- Modify: `server/game_state.py`
- Create: `tests/test_priority_stack.py`
- Create: `tests/test_card_effects.py`

**Interfaces:**
- Produces `PriorityStack.open(active_player, token)`, `grant(player_id, token)`, `act(player_id, token)`, `pass_priority(player_id, token)`, `push(item)`, and `pop()`.
- `pass_priority` returns `PriorityOutcome.TRANSFER`, `RESOLVE_TOP`, or `ADVANCE_STEP`.
- `GameEngine` handlers consume `CAST_SPELL`, `ACTIVATE_ABILITY`, `PRIORITY_PASS`, `TRIGGER_ORDER_RESPONSE`, and `TRIGGER_CHOICE_RESPONSE`.

- [ ] **Step 1: Add failing priority-token and pass tests**

```python
def test_two_passes_resolve_nonempty_stack_then_return_priority_to_ap(self):
    priority = PriorityStack(active_player="player_1", non_active_player="player_2")
    priority.open("player_1", 10)
    priority.push(StackItem(stack_item_id="stk_1", item_type="SPELL",
                            source="lightning_bolt_001",
                            controller="player_1", targets=["player_2"]))
    self.assertEqual(priority.pass_priority("player_1", 10).outcome, PriorityOutcome.TRANSFER)
    priority.grant("player_2", 11)
    self.assertEqual(priority.pass_priority("player_2", 11).outcome, PriorityOutcome.RESOLVE_TOP)
```

- [ ] **Step 2: Run priority tests and confirm missing-state-machine failures**

Run: `python -m unittest tests.test_priority_stack -v`

- [ ] **Step 3: Implement tokens, ownership, consecutive passes, and LIFO stack**

Return specific error codes for stale tokens and wrong holders. Acting resets consecutive passes and retains priority.

- [ ] **Step 4: Add failing cast, fizzle, state-based-action, and trigger tests**

Test phase/type legality, atomic mana-source tapping, target legality at cast and resolution, `STACK_PUSH`, `STACK_RESOLVE`, repeated lethal/toughness checks, AP/NAP trigger order, mandatory trigger ordering, and optional/targeted trigger choices before priority.

- [ ] **Step 5: Implement stack orchestration, state-based actions, and trigger requests**

Use server-generated stack/trigger IDs. Recheck all targets at resolution. Emit state changes and personalized snapshots after successful resolution.

- [ ] **Step 6: Add one failing behavior test per required effect**

```python
def test_lightning_bolt_deals_three_to_player(self): ...
def test_counterspell_removes_target_spell_from_stack(self): ...
def test_unsummon_returns_creature_to_owners_hand(self): ...
def test_giant_growth_expires_at_cleanup(self): ...
def test_gray_merchant_trigger_uses_black_mana_columns_for_devotion(self): ...
```

- [ ] **Step 7: Implement only the five selected effect handlers**

Use a base-ID effect dispatch table. Unsupported instants/sorceries return `ILLEGAL_ACTION`; unsupported permanent abilities remain unavailable while supported base statistics still function.

- [ ] **Step 8: Run Task 4 and full tests**

Run: `python -m unittest tests.test_priority_stack tests.test_card_effects -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 9: Review the Task 4 diff without committing**

Run: `git diff --check -- server tests`

---

### Task 5: Turns, Cleanup, Mana, and Combat

**Files:**
- Modify: `server/game_engine.py`
- Modify: `server/game_state.py`
- Modify: `server/priority_stack.py`
- Create: `tests/test_turn_combat.py`

**Interfaces:**
- Produces `GameEngine.begin_turn()`, `advance_step()`, `handle_play_land()`, `handle_discard()`, `handle_attackers()`, `handle_blockers()`, and `handle_damage_order()`.
- Produces deterministic combat `DamageEvent(source, target, amount)` results.

- [ ] **Step 1: Add failing phase-cycle tests**

Assert exact `UNTAP, UPKEEP, DRAW, PRECOMBAT_MAIN, BEGIN_COMBAT, DECLARE_ATTACKERS, DECLARE_BLOCKERS, ASSIGN_DAMAGE_ORDER, FIRST_STRIKE_DAMAGE, COMBAT_DAMAGE, END_OF_COMBAT, POSTCOMBAT_MAIN, END_STEP, CLEANUP` behavior, including conditional combat skips and required priority windows.

- [ ] **Step 2: Run turn tests and confirm missing-transition failures**

Run: `python -m unittest tests.test_turn_combat -v`

- [ ] **Step 3: Implement transitions, untap, first-turn draw skip, draw loss, and cleanup**

Broadcast each transition, reset land play at Untap, request repeated discard above seven, clear temporary effects/marked damage, rotate active player, and increment the turn.

- [ ] **Step 4: Add failing land/mana/phase tests**

Test one land per turn, main-phase-only land and sorcery-speed cards, instant timing, implicit mana-source validation/tapping, and `INSUFFICIENT_MANA`/`WRONG_PHASE` without mutation.

- [ ] **Step 5: Implement land and atomic mana payment**

Validate the submitted mana-payment mapping against untapped supplied mana sources and tap exactly those sources only on successful actions.

- [ ] **Step 6: Add failing combat tests**

Cover summoning sickness, Haste, attacker tapping, legal blockers, multiple blockers, required order, first strike, double strike engine support, simultaneous damage, lethal deaths, no trample, combat result fields, and End-of-Combat cleanup.

- [ ] **Step 7: Implement combat sub-state machine and damage calculation**

Allocate ordered blocker damage to remaining toughness before the next blocker, apply all step damage simultaneously, then run state-based actions and emit the specified result/update sequence.

- [ ] **Step 8: Run Task 5 and full tests**

Run: `python -m unittest tests.test_turn_combat -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 9: Review the Task 5 diff without committing**

Run: `git diff --check -- server tests`

---

### Task 6: Two-Seat Networking and Reconnection

**Files:**
- Modify: `server/connection_manager.py`
- Modify: `server/main.py`
- Create: `tests/test_connection_manager.py`

**Interfaces:**
- Produces `ConnectionEvent(kind, seat_id, pdu=None, error=None)`.
- Produces `ConnectionManager(host, port, event_queue, verbose, reconnect_timeout)`.
- Produces `accept_connections()`, `send(seat_id, pdu)`, `broadcast(pdu)`, `reserve_disconnected(seat_id)`, and `close()`.
- `server.main.GameServer` consumes queue events and delegates every valid PDU to `GameEngine.process`.

- [ ] **Step 1: Add failing two-seat/refusal tests**

Use loopback port zero. Connect two clients, assert distinct seats, attempt a third connection, and assert it cannot submit a game event.

- [ ] **Step 2: Run connection tests and confirm missing-manager failures**

Run: `python -m unittest tests.test_connection_manager -v`

- [ ] **Step 3: Implement listener, reader threads, queue tagging, and serialized writes**

Keep all game mutation outside reader threads. Convert framing failures into queue events. Make shutdown idempotent and unblock readers.

- [ ] **Step 4: Add failing heartbeat/disconnect/reclaim tests**

Test PING/PONG echo, inactivity deadlines, reserved seat, same-ID `PLAYER_READY` reclaim with state resync, wrong-ID refusal, third-client refusal, and timeout `GAME_OVER/DISCONNECT` while retaining the survivor.

- [ ] **Step 5: Implement connection timing and seat reclamation**

Use monotonic time, configurable short test deadlines, and an injected clock where needed. Route all PONG/error/game-over PDUs through the common sender and verbose logger.

- [ ] **Step 6: Wire `server/main.py`**

Support `--host`, `--port`, `--verbose`, and `--reconnect-timeout`; start the manager and game loop, print the listening address, and close cleanly on keyboard interruption.

- [ ] **Step 7: Run Task 6 and full tests**

Run: `python -m unittest tests.test_connection_manager -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 8: Review the Task 6 diff without committing**

Run: `git diff --check -- server tests`

---

### Task 7: GUI-Ready Client and Required CLI

**Files:**
- Create: `client/__init__.py`
- Modify: `client/network_client.py`
- Create: `client/state_store.py`
- Create: `client/controller.py`
- Modify: `client/ui.py`
- Modify: `client/main.py`
- Create: `tests/test_client.py`

**Interfaces:**
- Produces `ClientNetwork.connect()`, `send(pdu)`, `close()`, and callback registration.
- Produces `ClientStateStore.subscribe_state`, `subscribe_event`, `subscribe_error`, and `apply_pdu`.
- Produces `ClientController` methods matching every client-to-server action PDU.
- Produces `Command(name: str, args: tuple[str, ...])`.
- Produces `TerminalUI.run()` and `parse_command(line) -> Command` without direct socket access.

- [ ] **Step 1: Add failing store/controller contract tests**

```python
def test_state_update_replaces_snapshot_and_notifies_subscriber(self):
    seen = []
    store = ClientStateStore()
    store.subscribe_state(seen.append)
    store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 8,
                     "state": {"phase": "UPKEEP"}})
    self.assertEqual(seen[-1]["phase"], "UPKEEP")

def test_pass_priority_uses_latest_priority_token(self):
    sender = RecordingSender()
    controller = ClientController("player_1", sender, store_with_token(9))
    controller.pass_priority()
    self.assertEqual(sender.last, {"type": "PRIORITY_PASS", "seq_num": 9})
```

- [ ] **Step 2: Run client tests and confirm missing-layer failures**

Run: `python -m unittest tests.test_client -v`

- [ ] **Step 3: Implement state/event/error store and presentation-neutral controller**

Expose explicit command methods for all client-to-server PDUs. Select tokens by request category and keep a separate client counter for readiness/heartbeat where the RFC requires it.

- [ ] **Step 4: Add failing network-client tests**

Test framed send, receive callback, periodic PING, matching PONG tracking, timeout notification, disconnect notification, verbose records, and clean shutdown.

- [ ] **Step 5: Implement network client**

Keep reader/heartbeat threads independent of UI. Never call terminal functions from transport code.

- [ ] **Step 6: Add failing CLI parsing/rendering tests**

Cover `ready`, `keep`, `mulligan`, `land`, `cast`, `activate`, `pass`,
`attack`, `block`, `damage-order`, `trigger-order`, `trigger-choice`,
`discard`, `concede`, `state`, `help`, and `quit`; assert malformed input
produces user-facing guidance without a network PDU.

- [ ] **Step 7: Implement terminal adapter and client composition root**

Support `--host`, `--port`, `--id`, `--deck`, and `--verbose`. Render phase, turn, life, hand, public zones, stack, priority, and errors from notifications only.

- [ ] **Step 8: Run Task 7 and full tests**

Run: `python -m unittest tests.test_client -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 9: Review the Task 7 diff without committing**

Run: `git diff --check -- client tests`

---

### Task 8: End-to-End Demo and Deliverable Documentation

**Files:**
- Create: `tests/test_end_to_end.py`
- Create: `scripts/demo_game.py`
- Modify: `README.md`
- Create: `README.pdf`

**Interfaces:**
- `scripts.demo_game.run_demo(host, port) -> DemoResult` uses `ClientNetwork` and `ClientController` rather than private server APIs.
- `DemoResult` exposes observed PDU types, winner/reason, restart state, and verbose record counts.

- [ ] **Step 1: Add a failing real-socket end-to-end test**

Start the server on loopback port zero. Run two scripted clients through readiness, mulligan keep, turn transitions, land, Lightning Bolt, Counterspell response, stack resolution, combat, life-zero game over, return to lobby, and fresh readiness on retained connections.

- [ ] **Step 2: Run end-to-end test and confirm missing demo orchestration**

Run: `python -m unittest tests.test_end_to_end -v`

- [ ] **Step 3: Implement deterministic demo orchestration**

Use only public client commands and received state/events. Bound all waits with deadlines and include received-event diagnostics in assertion failures.

- [ ] **Step 4: Run end-to-end and full suites**

Run: `python -m unittest tests.test_end_to_end -v`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 5: Write README source content**

Include exact server/two-client commands, verbose mode, CLI commands, architecture, framing, sequence behavior, test commands, deterministic demo, five implemented effects, source hierarchy, all ambiguity resolutions, limitations, work-distribution matrix, and explicit AI usage describing Claude and Codex assistance.

- [ ] **Step 6: Render and visually verify `README.pdf`**

Generate the PDF from repository-owned README content, render every page to PNG, and inspect headings, tables, line wrapping, code blocks, page breaks, and legibility. Iterate until no clipping or overlap remains.

- [ ] **Step 7: Run final static and behavioral verification**

Run: `python -m compileall -q common server client tests scripts`

Run: `python -m unittest discover -s tests -v`

Run: `git diff --check`

Run: `rg -n "cite:|NotImplemented|^[[:space:]]*pass$" common server client tests scripts README.md`

- [ ] **Step 8: Review the complete uncommitted change set**

Run: `git status --short`

Run: `git diff --stat`

Confirm the implementation file list excludes `graphify-out/`, `tmp/`, secrets, caches, and debug artifacts. Do not stage or commit without user authorization.
