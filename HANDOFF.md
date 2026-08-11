# MTGNP project handoff

## Current status

- The required-scope, server-authoritative two-player MTGNP game is implemented in Python.
- The server supports the supplied lifecycle, mulligan, phase, priority, stack, combat, cleanup, game-over, reconnection, and restart requirements.
- The Tkinter GUI and terminal client share the same transport, authoritative state store, and presentation-neutral controller layers.
- The GUI uses 58 bundled card images from `client/assets/cards/` and does not make artwork API calls at runtime.
- The five required card effects are implemented: Lightning Bolt, Counterspell, Unsummon, Giant Growth, and Gray Merchant of Asphodel.
- The completed implementation is commit `247b820` (`feat: complete MTGNP RFC gameplay backend and tabletop GUI`).
- Commit `247b820` is on `origin/finished-test`. Local `main` also points to it, but `origin/main` is still one commit behind.

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

- `python -m compileall -q common server client tests scripts`
- `python -m unittest discover -s tests -v` — 105 tests passed.
- `python .superpowers\tools\verify_gui_e2e.py` — two GUI clients connected, entered gameplay, and successfully restarted to mulligan state.
- `python -m scripts.demo_game` — the scripted two-player game completed successfully.
- `git diff --check` and the staged diff check passed after documentation whitespace cleanup.
- The committed file set was scanned for common secret patterns; none were found.

The automated suite covers framing, all 25 PDU contracts, card-catalog integrity, hidden information, lifecycle and mulligans, priority and stack behavior, required card effects, turn phases, combat branches, connection limits, GUI projections and actions, Tk rendering, and real-loopback two-client behavior.

## Work remaining before final team handoff

1. Merge `finished-test` into the shared `main` branch, or otherwise move commit `247b820` to `origin/main` through the team's normal review workflow.
2. Run one complete manual game using two visible GUI windows on a teammate's normal Python/Tk installation. Exercise mulligans, land play, casting, stack responses, attackers, blockers, damage order, cleanup discard, game over, and restart.
3. ~~Regenerate or remove `README.pdf`~~ — Removed from repository and added to `.gitignore`. `README.md` is the canonical documentation source.
4. Review `THIRD_PARTY_NOTICES.md` and `client/assets/cards/manifest.json` before publicly publishing the bundled artwork.
5. Remove or keep local-only the untracked generated artifacts `test_results.txt` and `.impeccable/critique/`. The critique describes an earlier GUI state and contains findings already addressed by the current implementation.

## Intentional scope limits

- Only the five effects required by the supplied specification are implemented. Other instant, sorcery, triggered, and activated rules text from the supplied catalog remains unavailable because full card-effect coverage is bonus scope.
- The protocol schemas include activated-ability and trigger-order/choice PDUs, but the supported card subset does not provide generic activated abilities or optional/simultaneous trigger-decision flows.
- Authentication, TLS, spectators, matchmaking, persistence, and best-of-three matches are outside the supplied required scope.
- Combat does not implement bonus mechanics such as trample carry-over.

No additional backend feature work is currently known to be required by the supplied specifications. Any further code changes should be driven by the final manual acceptance game or new team requirements.
