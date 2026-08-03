# MTGNP GUI handoff

## Current status

- The two-client authoritative Python game and Tkinter GUI are implemented.
- Launch the server with `python -m server.main`.
- Launch each GUI client with `python -m client.gui_main`.
- The GUI uses 58 local card images in `client/assets/cards/`; it makes no artwork API calls at runtime.
- The terminal client remains available with `python -m client.main`.
- Nothing has been staged, committed, or pushed.

## Verified on 2026-08-04

- `python -m compileall -q common server client tests scripts`
- `python -m unittest discover -s tests -q` — 75 tests passed.
- `python .superpowers\tools\verify_gui_e2e.py` — two GUI clients connected and reached `UNTAP`; restart returned both clients to `MULLIGAN`.
- `git diff --check` — no whitespace errors; only Windows LF-to-CRLF warnings.
- Impeccable finish review: **PASS WITH NOTES**, with no critical or important findings.

## Remaining checks and optional polish

1. Run a manual game in two visible GUI windows on a normal teammate Python installation. The current sandbox needed local `TCL_LIBRARY`/`TK_LIBRARY` overrides because its Python Tcl/Tk installation is incomplete.
2. Exercise a full human game: mulligans, land play, casting, stack responses, attackers, blockers, damage order, discard, game over, and restart.
3. Optional minor UI polish from the reviewer:
   - Hide or disable a targeted-spell action when no legal target exists.
   - Change the empty attacker-selection label to “Declare no attackers.”
   - Replace native window chrome/fonts only if a more bespoke appearance is worth the extra complexity.
4. Complete the optional Impeccable documentation pass (`DESIGN.md` and `.impeccable/design.json`); it was stopped to conserve the remaining task budget.
5. Before any commit, review the working tree carefully. Keep planning/personal artifacts out of commits, especially `docs/superpowers/plans/`, `PRODUCT.md`, `graphify-out/`, and `.superpowers/`.
6. Review artwork licensing/attribution in `THIRD_PARTY_NOTICES.md` and `client/assets/cards/manifest.json` before publishing the repository.

## Suggested commit scope (only after team review)

Commit the runtime source, tests, decks, card assets, `README.md`, and `THIRD_PARTY_NOTICES.md`. Do not include planning or personal tooling artifacts. Stage an explicit file list rather than `git add .`.
