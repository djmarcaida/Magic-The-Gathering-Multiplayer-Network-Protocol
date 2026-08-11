# MTGNP project handoff

## Current status

- The required-scope, server-authoritative two-player MTGNP game is implemented in Python.
- The server supports the supplied lifecycle, mulligan, phase, priority, stack, combat, cleanup, game-over, reconnection, and restart requirements.
- The Tkinter GUI and terminal client share the same transport, authoritative state store, and presentation-neutral controller layers.
- The GUI uses 58 bundled card images from `client/assets/cards/` and does not make artwork API calls at runtime.
- The five required card effects are implemented: Lightning Bolt, Counterspell, Unsummon, Giant Growth, and Gray Merchant of Asphodel.
- Priority ownership is synchronized to both clients after every grant or pass. Only the authoritative holder sees priority actions, and a pending or rejected pass has an explicit recoverable GUI state.
- The turn header identifies the active player, land controls require both priority and the active player's main phase, selected hand cards stay above hovered cards, and tapped battlefield cards rotate while keeping their semantic outline.
- On Windows, the server exclusively owns its listening address. A second server cannot silently share port 4444 and split the two clients across separate games.
- Addressed all identified protocol-level RFC compliance gaps, ensuring exact schema match for `waiting_for`, `FIZZLE`, `TRIGGER_ABILITY`, `id`, `land_played_this_turn`, and `summoning_sickness`. The GUI model layer (`gui_model.py`) was also updated to consume the corrected wire-format field names.

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

- `python -m unittest discover -s tests` — 112 tests passed with Tcl/Tk enabled, fully verifying the updated RFC schemas.
- The real-loopback regression starts one server and two TCP clients, completes mulligan setup, transfers opening priority to the other player, and verifies that both projections agree while only the new holder retains a token.
- The duplicate-listener regression verifies that a second server cannot bind the first server's address.
- A live occupied-port check produced the intended clear startup error instead of creating another listener.
- The Impeccable UI detector reported no findings for `client/gui.py`.
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
8. Finish one complete visible match, including stack responses, attackers, blockers, damage, game over, and readying both retained connections for another mulligan.
9. Run the automated suite on a teammate's Python 3.12/Tk installation, then merge or cherry-pick the current `finished-test` commit through the team's normal review workflow.
10. Regenerate or remove `README.pdf` if the team intends to distribute it. It was last updated with the older August 4 implementation and does not match the current source documentation.
11. Review `THIRD_PARTY_NOTICES.md` and `client/assets/cards/manifest.json` before publicly publishing the bundled artwork.

## Intentional scope limits

- Only the five effects required by the supplied specification are implemented. Other instant, sorcery, triggered, and activated rules text from the supplied catalog remains unavailable because full card-effect coverage is bonus scope.
- The protocol schemas include activated-ability and trigger-order/choice PDUs, but the supported card subset does not provide generic activated abilities or optional/simultaneous trigger-decision flows.
- Authentication, TLS, spectators, matchmaking, persistence, and best-of-three matches are outside the supplied required scope.
- Combat does not implement bonus mechanics such as trample carry-over.

No additional backend feature work is currently known to be required by the supplied specifications. Any further code changes should be driven by the manual acceptance tests above or new team requirements.
