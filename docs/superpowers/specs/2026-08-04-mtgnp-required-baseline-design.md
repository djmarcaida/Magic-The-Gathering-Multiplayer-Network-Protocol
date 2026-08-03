# MTGNP Required Baseline Design

**Date:** 2026-08-04

**Status:** Approved for implementation planning

**Scope:** Required MTGNP v1.0 and grading-rubric behavior only

## Objective

Build a server-authoritative, two-player Magic: The Gathering Multiplayer
Network Protocol implementation in Python. The deliverable consists of one
server process and two terminal client processes communicating over TCP. It
implements the required RFC and rubric baseline without GUI, spectator,
complete-card-effect, or other bonus features.

The client architecture must remain presentation-independent so a future GUI
can replace the CLI without changing networking, protocol handling, or game
rules.

## Authoritative Sources

Game and protocol behavior must come only from these supplied artifacts:

1. `C:\Users\xenob\Downloads\CSNETWK_MP_MTGNP.pdf` is authoritative for
   transport, lifecycle, PDU schemas, game rules, grading, and deliverables.
2. `C:\Users\xenob\Downloads\mtgnp_master_card_list.pdf` is authoritative for
   legal card IDs, costs, statistics, keywords, and simplified effects.
3. `C:\Users\xenob\Downloads\Prompt.pdf` is a planning aid. It cannot override
   the RFC or rubric.
4. The existing repository establishes the starting file organization.

No external Magic card database, rules engine, rules website, card API, or
gameplay library will supply behavior or data. Python standard-library APIs may
be used to implement sockets, threads, queues, JSON, command parsing, and tests.

When supplied examples conflict with normative text, the formal RFC rules and
Section 10 schemas take precedence. Every remaining interpretation is recorded
in this document and later in the project README.

## Scope

### Included

- One server and exactly two active TCP client connections on default port 4444.
- Four-byte big-endian length-prefixed UTF-8 JSON framing with a 65,535-byte
  payload limit.
- All 25 PDU types and all RFC error codes.
- Server and client verbose modes that label every sent and received PDU.
- `LOBBY -> GAME_SETUP -> MULLIGAN -> IN_GAME -> GAME_OVER -> LOBBY`.
- Server-side deck validation, shuffling, seven-card opening hands, 20 life,
  first-player selection, and repeated London mulligans.
- Complete turn, priority, stack, trigger, state-based-action, combat, cleanup,
  win-condition, heartbeat, disconnect, reconnect, and restart behavior required
  by the RFC and rubric.
- Personalized client-visible state that never exposes the opponent's hand.
- The complete supplied catalog of 58 base cards and 312 legal card instances
  for validation.
- Exactly the rubric-required minimum of five implemented nontrivial card
  effects, plus generic land, permanent, creature, keyword, and combat behavior.
- Automated unit, integration, and real-socket end-to-end tests.
- Source README plus the required rendered README PDF.

### Excluded

- Graphical UI in the current deliverable.
- Spectator clients.
- Implementing all supplied card abilities and effects.
- Match or best-of-three structure.
- Authentication, TLS, planeswalkers, replacement effects, and trample.
- Any other bonus feature not required for the 100-point baseline.

## Architecture

### Server

The server uses independent socket-reader threads for network concurrency and a
single authoritative game-loop thread for state mutation.

Each reader decodes and validates the transport envelope, tags the resulting
PDU with its connection and seat identity, and places an event on a shared
queue. Only the game loop may mutate `GameState`. This makes simultaneous client
traffic deterministic and prevents game-state races without pervasive locks.

The server is divided into focused units:

- `common/framing.py`: exact-byte reads, frame encoding/decoding, size checks,
  JSON handling, and verbose transport logging.
- `common/pdus.py`: PDU names, directions, required fields, constructors, and
  runtime schema validation for all 25 types.
- `server/connection_manager.py`: listener, two-seat registry, reader lifetime,
  outbound socket serialization, heartbeats, disconnects, and seat reclamation.
- `server/game_state.py`: dataclasses for players, zones, permanents, stack
  items, combat assignments, priority tokens, turn state, and visible snapshots.
- `server/priority_stack.py`: priority holder, consecutive passes, LIFO stack,
  fizzle checks, trigger ordering/choices, and request-token validation.
- `server/game_engine.py`: lifecycle, phases, actions, card resolution,
  state-based actions, combat, win checks, and outbound domain events.
- `server/main.py`: argument parsing, dependency wiring, startup, and shutdown.
- `cards.json`: catalog data derived only from the supplied master card list.

All outbound messages pass through one server PDU sender so sequence numbers,
framing, personalization, and verbose logging cannot diverge across subsystems.

### Client and Future GUI Boundary

The client has four layers:

- `client/network_client.py` owns TCP, framing, receive/background heartbeat
  work, and raw PDU callbacks. It contains no presentation or game rules.
- A client state store replaces its visible snapshot whenever it receives a
  `GAME_STATE_UPDATE` and publishes state/event/error notifications.
- A client controller exposes presentation-neutral commands such as
  `send_ready`, `choose_mulligan`, `play_land`, `cast_spell`,
  `activate_ability`, `pass_priority`, `declare_attackers`,
  `declare_blockers`, `assign_damage_order`, `discard`, and `concede`.
- `client/ui.py` implements the required terminal view and command parser using
  only the controller and state-store notifications.

A future GUI will implement the same view/subscriber boundary and call the same
controller methods. GUI event-loop marshalling belongs in that future adapter;
the protocol and application layers remain unchanged.

### Shared Presentation Contract

The state store exposes three notification categories:

- state replacement with the newest personalized state snapshot;
- protocol/game event notification for transitions, stack events, combat, and
  game over;
- recoverable error notification for `ERROR` PDUs and connection status.

The CLI and any future GUI render notifications but never calculate legality,
damage, stack resolution, or victory.

## Connection Model

- The server keeps a listener open while maintaining exactly two seats.
- Each occupied seat has at most one active socket and one reader thread.
- A third connection is refused while both seats are active or reserved.
- Every inbound event carries its seat identity; a client-supplied player ID
  never grants authority over another socket's seat.
- Outbound writes to each socket are serialized to prevent frame interleaving.
- Heartbeat and socket failures become game-loop connection events.
- A disconnected seat is reserved for an implementation-defined grace period.
- Because the RFC defines no reconnect PDU, a replacement socket reclaims the
  reserved seat by sending `PLAYER_READY` with the same non-empty `player_id`.
  The server then sends a personalized authoritative state snapshot and resumes.
- Failure to reclaim the seat before the deadline produces `GAME_OVER` with
  reason `DISCONNECT`; the surviving connection is retained for the next lobby.

This reconnect handshake is an explicit implementation interpretation and will
be documented as such.

## Protocol and Data Flow

For every client action:

1. The CLI invokes a controller command.
2. The controller constructs the required PDU with the latest applicable
   priority or request token.
3. The network client frames and sends the PDU.
4. The corresponding server reader decodes it and queues a seat-tagged event.
5. The game loop validates its PDU shape, token, priority holder, phase, cost,
   targets, and game rule.
6. A valid action mutates authoritative state and emits the required event PDUs
   and personalized state updates.
7. An invalid action leaves state unchanged and sends only the originating
   client an `ERROR`. If that player still holds priority, the server reissues
   `PRIORITY_GRANT` with the same token.
8. Each client replaces its local visible state on `GAME_STATE_UPDATE` and
   notifies its active presentation adapter.

Accepted actions that change visible state are followed by the RFC-required
event messages and personalized `GAME_STATE_UPDATE` messages. Rejected actions
do not generate a misleading state change.

## PDU and Sequence Rules

The implementation covers these exact message names:

`PLAYER_READY`, `GAME_STATE_UPDATE`, `MULLIGAN_CHOICE`, `PHASE_TRANSITION`,
`PRIORITY_GRANT`, `PRIORITY_PASS`, `CAST_SPELL`, `ACTIVATE_ABILITY`,
`STACK_PUSH`, `TRIGGER_ORDER`, `TRIGGER_ORDER_RESPONSE`, `TRIGGER_CHOICE`,
`TRIGGER_CHOICE_RESPONSE`, `STACK_RESOLVE`, `DECLARE_ATTACKERS`,
`DECLARE_BLOCKERS`, `ASSIGN_DAMAGE_ORDER`, `COMBAT_DAMAGE_RESULT`, `PLAY_LAND`,
`DISCARD`, `CONCEDE`, `GAME_OVER`, `ERROR`, `PING`, and `PONG`.

- Every parsed PDU requires exact, case-sensitive `type` and integer `seq_num`
  fields unless parsing fails before an object exists.
- Server-issued PDUs use the server's monotonically increasing sequence
  counter, except an error retry explicitly reuses the still-current priority
  token as required by Section 11.
- Priority actions echo the latest applicable `PRIORITY_GRANT` token.
- Mulligan, discard, trigger response, and combat declaration PDUs echo their
  specific requesting server PDU as defined by Section 5.4.
- `CONCEDE` may be sent at any time and echoes the most recently received server
  PDU sequence number.
- Heartbeat messages use their request/echo semantics without becoming priority
  actions.

## Authoritative Game State

The server state contains:

- lifecycle state, turn number, active player, phase/step, priority holder, and
  current request token;
- each player's ID, life, library order, hand, battlefield, graveyard, mana
  payment sources, land-play flag, and mulligan count;
- public stack items from bottom to top;
- triggered-ability decisions;
- combat attackers, blockers, damage order, marked damage, and temporary effects;
- connection and timeout status.

Personalized snapshots include the receiving player's hand, public battlefield,
graveyards, stack, life totals, counts, phase, turn, active player, and priority
holder. The opponent's hand is represented only by its count. Library order is
never transmitted.

## Lifecycle and Turn Engine

### Lobby and Setup

- Both seats submit valid `PLAYER_READY` PDUs before setup begins.
- Player IDs are non-empty and unique within the lobby.
- Decks contain 1-50 instance IDs from the supplied catalog. Duplicate instance
  IDs within a submitted deck are rejected because each ID identifies one
  physical catalog instance.
- A later valid `PLAYER_READY` from the same seat replaces its earlier lobby
  submission.
- Setup initializes life to 20, shuffles both decks using server-side randomness,
  draws opening hands, and chooses the first player randomly.

### Mulligan

Each player independently sends `MULLIGAN_CHOICE`. `keep: false` returns the
current hand to the library, reshuffles, and draws a fresh opening hand.
`keep: true` after N mulligans requires exactly N current-hand card IDs in
`cards_to_bottom`. For the RFC's contradictory 1-6-card deck edge case, the
required number is capped at the current hand size so a player can eventually
keep. The game begins only after both players keep.

### Turns

The exact turn order is:

`UNTAP -> UPKEEP -> DRAW -> PRECOMBAT_MAIN -> COMBAT -> POSTCOMBAT_MAIN -> END_STEP -> CLEANUP`

Untap and Cleanup do not grant priority. All other required windows begin with
the active player. The first player skips the card draw on turn one but still
enters Draw and receives the required priority window.

Cleanup requests discards until the active player's hand has at most seven
cards, clears remaining marked damage and end-of-turn effects, increments the
turn, switches active player, and starts Untap.

## Priority, Stack, Triggers, and State-Based Actions

- The active player receives priority first in each priority window.
- Acting retains priority; passing transfers priority.
- Two consecutive passes with a non-empty stack resolve exactly the top item,
  apply state-based actions and triggers, then return priority to the active
  player.
- Two consecutive passes with an empty stack advance the step.
- Stack items are LIFO and expose the RFC-required public fields.
- Resolution revalidates targets; an item with no remaining legal target
  fizzles.
- State-based actions repeat until stable before priority is issued.
- Required checks include life at or below zero, toughness at or below zero,
  and lethal marked damage.
- Simultaneous triggers use active-player/non-active-player ordering.
- Multiple triggers controlled by one player use `TRIGGER_ORDER` and
  `TRIGGER_ORDER_RESPONSE`.
- Optional or targeted triggers use `TRIGGER_CHOICE` and
  `TRIGGER_CHOICE_RESPONSE` before stack placement.

## Combat

Combat contains Begin Combat, Declare Attackers, Declare Blockers, conditional
Assign Damage Order, conditional First Strike Damage, Combat Damage, and End of
Combat.

- Only legal, untapped, non-summoning-sick creatures may attack unless Haste
  removes the summoning-sickness restriction.
- Attacking taps the creature.
- An untapped creature blocks at most one attacker; multiple blockers may block
  one attacker.
- A multiply blocked attacker assigns damage in the submitted blocker order.
  Damage is allocated to each blocker up to its remaining toughness before
  continuing to the next blocker. No trample damage carries to the player.
- First-strike creatures deal damage in the conditional first-strike step;
  double-strike support in the combat engine permits damage in both steps.
- Regular combat damage is simultaneous, followed by state-based actions,
  result/state broadcasts, and the End of Combat transition.
- End of Combat clears attacker/blocker assignments and combat damage marked
  during combat. Cleanup also clears damage, which is intentionally idempotent
  and covers damage applied after combat.

## Card Catalog and Required Effects

`cards.json` is populated exclusively from the supplied master card list. It
contains the 58 base definitions and all 312 individual protocol card IDs.

The five required nontrivial effects are:

1. Lightning Bolt: three damage to a legal target.
2. Counterspell: counter a target spell on the stack.
3. Unsummon: return a target creature to its owner's hand.
4. Giant Growth: target creature gets +3/+3 until end of turn.
5. Gray Merchant of Asphodel: enters-the-battlefield trigger that drains the
   opponent by the controller's black devotion and grants that much life to its
   controller. Black devotion is the total number of black mana symbols in the
   costs of permanents that player controls, using the card-list mana columns.

Basic lands, implicit mana payment, ordinary permanent resolution, vanilla
creatures, combat statistics, Haste, First Strike, and other behavior needed to
exercise required engine paths are core mechanics rather than bonus effects.

All catalog IDs remain legal deck entries. The provided demo decks use only
cards whose necessary behavior is implemented. Unimplemented ability text is
listed as a known limitation rather than silently supplemented from external
Magic rules. Permanents with unsupported abilities use only their supported
base type, cost, power, toughness, and keywords. Casting an instant or sorcery
whose effect is unsupported is rejected with `ILLEGAL_ACTION` and a clear
message; it never resolves as a silent no-op.

## Error Handling

The server supports all specified error codes:

`INVALID_JSON`, `ILLEGAL_DECK`, `UNKNOWN_TYPE`, `STALE_ACTION`,
`NOT_YOUR_PRIORITY`, `ILLEGAL_ACTION`, `ILLEGAL_TARGET`,
`TRIGGER_ORDER_INVALID`, `TRIGGER_CHOICE_INVALID`, `INSUFFICIENT_MANA`,
`WRONG_PHASE`, and `DUPLICATE_ID`.

An invalid action is discarded without state mutation. The `ERROR` includes a
readable message and the rejected action when it was parseable. The client
displays the error and remains connected.

Unparseable UTF-8/JSON has no recoverable action object or request token. The
server therefore sends `INVALID_JSON` using its next server sequence number and
`rejected_action: null`. An announced payload larger than 65,535 bytes is a
fatal framing violation: the server sends an error when safely possible, closes
that socket to avoid reading an unbounded payload, and enters the normal
reconnect flow. Both are documented RFC interpretations.

## Explicit RFC Ambiguity Resolutions

The following choices prevent implementation drift:

1. Normative RFC prose and Section 10 schemas override the sample appendix.
2. The first player does not draw on turn one even though one appendix exchange
   shows a draw.
3. Formal Section 10 field names and shapes are canonical when examples drift.
4. `MULLIGAN` is accepted as the initial `from_phase` when entering `UNTAP`,
   despite its omission from one enumerated example.
5. Decks of 1-6 cards remain valid because the RFC explicitly permits 1-50.
   Opening-hand setup and mulligans draw up to the available deck size without
   causing `DECK_EMPTY`; that loss condition applies to required in-game draws.
   If the mulligan count exceeds the resulting hand size, the required
   `cards_to_bottom` count is capped at that hand size so the lifecycle cannot
   become impossible to complete.
6. Reconnection uses same-player-ID `PLAYER_READY` seat reclamation because no
   separate reconnect PDU exists.
7. Combat damage is allocated through blocker order as described above; no
   undocumented trample behavior is added.
8. The Combat Damage step itself does not open an extra response window; the
   server proceeds to End of Combat and opens the priority window there, matching
   the normative prose.
9. Combat damage is cleared at End of Combat and Cleanup remains an idempotent
   second clearing point for later marked damage.
10. Oversized and unparseable frames follow the error behavior described above.

## Testing Strategy

The project uses `unittest` and standard-library test doubles.

### Unit Tests

- partial reads, combined frames, exact-byte reads, size limits, UTF-8, JSON,
  and verbose framing output;
- schema validation and round-trip construction for all 25 PDUs;
- card catalog completeness and card-instance uniqueness;
- lifecycle, mulligan, phase, priority, stack, trigger, effect, state-based
  action, combat, cleanup, and victory transitions using injected deterministic
  randomness;
- personalized state filtering;
- controller/state-store notification behavior independent of the CLI.

### Integration Tests

- connection manager plus game engine using socket pairs or loopback sockets;
- simultaneous/stale client actions around a priority token;
- heartbeat, timeout, disconnect, seat reclaim, and timeout loss;
- verbose logging on all client/server send and receive paths;
- invalid action recovery without state mutation or disconnect.

### End-to-End Test

One real server and two scripted clients complete:

1. connections and lobby readiness;
2. setup and mulligans;
3. multiple phases and at least one full turn;
4. land play, spell casting, a response on the stack, and resolution;
5. combat;
6. a life-zero game over;
7. return to lobby and a fresh same-connection game start.

The test asserts the expected event order, personalized visibility, verbose
records, and absence of unhandled exceptions.

## Documentation and Delivery

The repository will contain:

- build and run instructions for one server and two clients;
- startup examples with verbose mode enabled;
- CLI command reference and demo sequence;
- architecture and protocol explanations suitable for the team demonstration;
- test commands and expected outcomes;
- work-distribution matrix;
- complete AI-usage disclosure;
- known limitations and every RFC interpretation listed above;
- source README and visually verified README PDF.

Implementation work will not include unrelated repository cleanup or bonus
features.
