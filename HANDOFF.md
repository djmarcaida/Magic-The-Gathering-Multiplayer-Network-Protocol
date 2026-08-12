# MTGNP project handoff

## Current status

- The required-scope, server-authoritative two-player MTGNP game is implemented in Python.
- The server supports the supplied lifecycle, mulligan, phase, priority, stack, combat, cleanup, game-over, reconnection, and restart requirements.
- The Tkinter GUI and terminal client share the same transport, authoritative state store, and presentation-neutral controller layers.
- The GUI uses 58 bundled card images from `client/assets/cards/` and does not make artwork API calls at runtime.
- The five required card effects are implemented: Lightning Bolt, Counterspell, Unsummon, Giant Growth, and Gray Merchant of Asphodel.
- Priority ownership is synchronized to both clients after every grant or pass. Only the authoritative holder sees priority actions, and a pending or rejected pass has an explicit recoverable GUI state.
- Battlefield snapshots no longer fail when a permanent has summoning sickness; the GUI applies that state only to creatures and continues processing stack-resolution updates for both players.
- Lightning Bolt and Rift Bolt share a player-or-creature targeting path. The opponent is the first player choice, lands are excluded by both GUI and server validation, and Rift Bolt opens its required target prompt.
- Combat declarations filter persistent mixed selections down to legal creatures. The required player always has an explicit no-attackers or no-blockers action, and declaration phases are labeled as choices rather than priority waits.
- Stale direct-phase requests return a fresh personalized state/request token for attacker, blocker, damage-order, and required-cleanup actions, allowing a retry instead of leaving the match stuck.
- The turn header identifies the active player, land controls require both priority and the active player's main phase, selected hand cards stay above hovered cards, and tapped battlefield cards rotate while keeping their semantic outline.
- On Windows, the server exclusively owns its listening address. A second server cannot silently share port 4444 and split the two clients across separate games.
- Identified protocol-level RFC gaps were addressed for `waiting_for`, `FIZZLE`, `TRIGGER_ABILITY`, `id`, `land_played_this_turn`, and `summoning_sickness`; the GUI consumes those wire-format fields.

## Running the project

Run all commands from the repository root with Python 3.12 or newer.

```powershell
python -m server.main
python -m client.gui_main
python -m client.gui_main
```

Each GUI client runs in a separate process. The terminal client remains available with:

```powershell
python -m client.main
```

The desktop client requires Python's optional Tcl/Tk component.

## Verification completed on 2026-08-12

- `python -m unittest discover` - 116 tests passed and 12 Tk visual smoke tests skipped because this machine's Python installation could not find `init.tcl`.
- `python -m compileall -q client common server tests` passed.
- Focused regressions cover summoning-sick creature projection, Rift Bolt targeting, rejection of land targets for burn spells, mixed Ornithopter-plus-land attacker selection, explicit no-attacker/no-blocker actions, and retrying a stale blocker request with the refreshed token.
- The real-loopback regression starts one server and two TCP clients, completes mulligan setup, transfers opening priority, and verifies that both projections agree while only the holder retains a token.
- The duplicate-listener regression verifies that a second server cannot bind the first server's address.
- A live occupied-port check produced the intended clear startup error instead of creating another listener.
- The Impeccable UI detector reported no findings for `client/gui.py` in the preceding UI review.
- `git diff --check` passed.

The automated suite covers framing, all 25 PDU contracts, card-catalog integrity, hidden information, lifecycle and mulligans, priority and stack behavior, required card effects, turn phases, combat branches, connection limits, GUI projections and actions, Tk rendering, and real-loopback two-client behavior.

## Manual tests still required before final team handoff

1. Close every old server and client process. Start exactly one server on port 4444, then open two GUI clients. Confirm the first client remains in the lobby until the second connects and submits a deck.
2. While that server is running, try to start another server on port 4444. Confirm it exits with `Close the existing server or choose a different port.` and does not accept either client.
3. Complete mulligans with both visible clients. Confirm the randomly selected active player receives opening priority and both windows name the same holder.
4. Pass priority in both directions several times. The sender should immediately show `Passing priority...`, lose the pass button, then display the other holder. Only the recipient should show `Your priority` and `Pass priority`.
5. Advance through a complete turn. Confirm only the active player can play a land during either main phase, while the non-active player may only use legal priority responses such as supported Instants.
6. Play and tap a land or declare a non-vigilance attacker. Confirm the battlefield card rotates clockwise, retains its color/selection outline, and returns upright during its controller's next untap step.
7. Select a hand card and hover adjacent cards. Confirm the selected card remains visually on top and its outline is not obscured.
8. Cast a creature and let it resolve. Confirm both windows continue updating without `name 'base_card' is not defined`. On a later turn, leave a land selected with an untapped Ornithopter; confirm the attack action remains available and submits only Ornithopter.
9. At Declare Attackers and Declare Blockers, confirm the required player sees `Choose attackers` or `Choose blockers`, the other player sees an explicit waiting message, and the no-attackers/no-blockers action advances combat.
10. Cast Lightning Bolt and Rift Bolt. Confirm the opponent is the initial player target, creatures are available, lands are unavailable, and a manually submitted land target is rejected.
11. Exercise a stale declaration request using a delayed or repeated action. Confirm the client receives a fresh state token and can retry. Heartbeat `Pong` events must not replace the declaration token.
12. Finish one complete visible match, including stack responses, attackers, blockers, damage, game over, and readying both retained connections for another mulligan.
13. Run the automated suite on a teammate's Python 3.12/Tk installation so the 12 visual smoke tests execute, then merge or cherry-pick the reviewed commit through the team's normal workflow.
14. Regenerate or remove `README.pdf` if the team intends to distribute it. It was last updated with the older August 4 implementation and does not match the current source documentation.
15. Review `THIRD_PARTY_NOTICES.md` and `client/assets/cards/manifest.json` before publicly publishing the bundled artwork.

## Intentional scope limits

- Only the five effects required by the supplied specification are implemented. Other instant, sorcery, triggered, and activated rules text from the supplied catalog remains unavailable because full card-effect coverage is bonus scope.
- The protocol schemas include activated-ability and trigger-order/choice PDUs, but the supported card subset does not provide generic activated abilities or optional/simultaneous trigger-decision flows.
- Authentication, TLS, spectators, matchmaking, persistence, and best-of-three matches are outside the supplied required scope.
- Combat does not implement bonus mechanics such as trample carry-over.

No additional backend feature work is currently known to be required by the supplied specifications. Further code changes should be driven by the manual acceptance tests above or new team requirements.
