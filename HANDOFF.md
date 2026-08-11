# MTGNP project handoff

## Current status

- The required-scope, server-authoritative two-player MTGNP game is fully implemented in Python.
- The server supports the supplied lifecycle, mulligan, phase, priority, stack, combat, cleanup, game-over, reconnection, and restart requirements.
- The Tkinter GUI and terminal client share the same transport, authoritative state store, and presentation-neutral controller layers.
- The GUI uses 58 bundled card images from `client/assets/cards/` and does not make artwork API calls at runtime.
- The five required card effects are implemented: Lightning Bolt, Counterspell, Unsummon, Giant Growth, and Gray Merchant of Asphodel.
- `finished-test` is merged into `main` and all branches (`main`, `finished-test`) are synced with `origin`.

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

- `python -m compileall -q common server client tests scripts` — clean compilation.
- `python -m unittest discover -s tests -v` — 105 tests passed cleanly.
- `python .superpowers\tools\verify_gui_e2e.py` — two GUI clients connected, entered gameplay, and successfully restarted to mulligan state.
- `python -m scripts.demo_game` — the scripted two-player game completed successfully.
- `python -m scripts.build_readme_pdf` — `README.pdf` regenerated and matches current `README.md`.
- `git diff --check` — no trailing whitespace or diff issues.
- `THIRD_PARTY_NOTICES.md` and `client/assets/cards/manifest.json` reviewed for artwork licensing.
- The committed file set was scanned for common secret patterns; none were found.

The automated suite covers framing, all 25 PDU contracts, card-catalog integrity, hidden information, lifecycle and mulligans, priority and stack behavior, required card effects, turn phases, combat branches, connection limits, GUI projections and actions, Tk rendering, and real-loopback two-client behavior.

## Completed handoff checklist items

1. **Branch Sync & Merge:** Merged `finished-test` into `main` and synced `origin/main` and `origin/finished-test`.
2. **Verification Suite:** All 105 unit tests, GUI E2E verification script, and demo game script executed and passed cleanly.
3. **Documentation:** `README.pdf` regenerated using `scripts/build_readme_pdf.py` to match the latest `README.md`.
4. **Licensing & Notices:** Reviewed `THIRD_PARTY_NOTICES.md` and `client/assets/cards/manifest.json` for proper Fan Content and Scryfall attribution.
5. **Artifact Cleanliness:** Working tree is clean and free of leftover local debug artifacts.

## Intentional scope limits

- Only the five effects required by the supplied specification are implemented. Other instant, sorcery, triggered, and activated rules text from the supplied catalog remains unavailable because full card-effect coverage is bonus scope.
- The protocol schemas include activated-ability and trigger-order/choice PDUs, but the supported card subset does not provide generic activated abilities or optional/simultaneous trigger-decision flows.
- Authentication, TLS, spectators, matchmaking, persistence, and best-of-three matches are outside the supplied required scope.
- Combat does not implement bonus mechanics such as trample carry-over.

No additional backend feature work is required. The project is ready for team delivery.
