# MTGNP Tkinter Tabletop Upgrade Design

> Superseded by the sprite-first, resource-first decisions in `docs/superpowers/plans/2026-08-11-mtgnp-tkinter-tabletop-upgrade-revised.md`.

## Goal

Make every card immediately identifiable and make turn decisions safer and faster while preserving the authoritative server, standard-library Tkinter, local card artwork, and terminal client.

## Card interaction

Only the player's hand becomes a fanned hand. It uses overlapping, vertically staggered card tiles in a horizontally scrollable canvas; it does not rotate raster artwork. A selected card is raised above the fan and uses a larger cached image. Battlefield and opponent zones remain straight strips so permanents are easy to scan.

Every visible tile shows three caption rows: card name; `Mana: <compact cost> · <type>` with power/toughness for creatures; and explicit state text such as `Tapped`, `3 damage`, or `Summoning sick`. Empty mana costs render as `Mana: —`. Selection is represented by raised position, larger image, border, text, and keyboard focus—not color alone.

Selecting a card updates a `Selected card` panel above the action buttons. The panel displays its name, mana cost, type/subtype, power/toughness when applicable, keywords, status, and rules text. Multi-selection still works for discard, attackers, and blockers; the most recently selected card is the detail focus. Double-click and Enter retain a full detail dialog; the dialog gains a Close button and Escape binding.

## Safety, recovery, and layout

Blocker assignment begins with an explicit `Choose attacker…` value and cannot be submitted until all selected blockers have an intentional assignment. On disconnect, the UI closes the failed network once, clears controller/session state, disables game controls, and returns to the connection form with the previous host, port, player ID, and deck path retained.

At compact widths, the game shell must remain navigable: the board remains vertically scrollable, the hand continues horizontal scrolling, and the phase rail is grouped into Beginning, Combat, and Ending with the active phase prominent. The action panel is reachable without clipping. The GUI processes network callbacks in bounded batches and retains a bounded activity history.

## Constraints and verification

- No gameplay/rule calculation or authority moves into the client.
- No runtime dependencies or web calls are added.
- Preserve the user's current uncommitted `client/gui.py` mana/type work and evolve it into the final captions.
- Add pure unit tests for presentation/layout helpers and Tk smoke tests for interactive behavior when Tcl/Tk is available.
- Verify with focused GUI tests, the complete unit suite, `python -m compileall -q common server client tests scripts`, and `git diff --check`.
