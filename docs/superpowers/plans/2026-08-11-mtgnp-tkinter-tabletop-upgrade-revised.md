# MTGNP Tkinter Tabletop Upgrade — Revised Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task. This revision supersedes `2026-08-11-mtgnp-tkinter-tabletop-upgrade.md`.

**Goal:** Keep card sprites visually clean and readable while making the live game state—life, zones, usable mana sources, phase, priority, and selection—easy to scan.

**Architecture:** The GUI remains a pure presentation of authoritative snapshots. `client.gui_model` gains only deterministic presentation helpers: card-border color and a resource summary derived from the snapshot's visible battlefield. No client-side rules or mana pool is created; the game currently has no persistent mana-pool field.

**Tech stack:** Python 3.12, standard-library Tkinter/ttk, unittest, bundled PNG card sprites. No new dependencies or runtime web access.

## Implementation status — 2026-08-11

Implemented in the current worktree, including the later interaction refinement: native Tk buttons display cached rounded composites at approximately 180×251 pixels normally, 200×279 on hover, and 216×301 when selected. The hand uses a four-position viewport with direct wheel navigation; duplicate Previous/Next controls and visible card-strip scrollbars were removed. The outer game scroll canvas was also removed, while compact battlefield previews keep the full board and action panel inside the fixed desktop composition. Rounded-image processing falls back to the original sprite rather than replacing the input widget. The model/action/network regressions and full automated suite pass. Tk-dependent smoke tests are present but skipped on the current machine because its Python installation cannot locate `init.tcl`; the manual two-client visual checklist therefore remains open.

## Locked design decisions

- Player-hand cards are a horizontally scrollable, fanned row. Normal sprites render at approximately 144×201 pixels so their printed content remains legible. Clicking a card selects it; the selected card lifts, enlarges to approximately 180×251 pixels, receives a thicker ring in its own semantic card-outline color, and stays in view.
- Card sprites provide card name, mana cost, type, stats, and rules text. Do **not** render metadata captions or a selected-card rules/details panel below/beside sprites.
- Every card tile receives a semantic border from its catalog color: white `#F3DF9B`, blue `#63A8D5`, black `#997AAF`, red `#D76A5B`, green `#63AA73`, colorless `#AFB5B1`, multicolor `#D5AD49`.
- Move player statistics into compact icon-and-text strips immediately above their respective battlefields. Opponent strip: public life, hand, library, graveyard, and exile. Player strip: the same values plus land-play status, permanent count, and `Potential mana`. The right panel contains only actions and activity.
- The repository has no separate status-icon assets; draw local, dependency-free glyphs/canvas marks for life, hand, library, graveyard, and exile, then pair every glyph with visible text. Render mana as colored lettered `W/U/B/R/G/C` pips with counts; do not download or embed unbundled official icon art.
- Remove the left phase rail. In the header, show a fixed-width phase strip: muted previous phase, arrow, prominent current phase, arrow, muted next phase. On a consecutive server phase change, slide all three labels toward the previous phase over 150 ms, then replace their text. Skip the animation for an initial state, a skipped/non-adjacent update, or a backward/restarted lifecycle update. The server snapshot is applied immediately; animation never delays controls or invents a phase.
- `Potential mana` is explicitly not a mana pool. Derive it only from the same untapped sources that `GameEngine._validate_mana_payment` recognizes: Mountain/R, Island/U, Forest/G, Swamp/B, Plains/W, Sol Ring/C×2.
- Keep the previously identified reconnect recovery, safe blocker assignment, keyboard paths, compact layout, bounded event bridge, and bounded activity log.
- Preserve the existing uncommitted `client/gui.py` work unless this revision deliberately replaces its metadata captions with sprite-only tiles. Do not stage, commit, or push without owner authorization.

---

## Task 1: Pure resource and color projections

**Files:**
- Modify: `client/gui_model.py`
- Modify: `tests/test_gui_model.py`

**Interfaces:**

```python
def card_border_color(card: CardView) -> str: ...

@dataclass(frozen=True)
class ResourceSummary:
    life: int
    hand_count: int
    library_count: int
    graveyard_count: int
    exile_count: int
    land_played: bool
    permanent_count: int
    mana_sources: Mapping[str, int]

def resource_summary(player: PlayerView) -> ResourceSummary: ...

def phase_neighbors(phase: str) -> tuple[str, str, str]: ...
```

- [ ] **Step 1: Write failing color tests.**

```python
def test_card_border_color_uses_catalog_colors(self):
    self.assertEqual(card_border_color(CardView.from_instance("lightning_bolt_001", self.catalog)), "#D76A5B")
    self.assertEqual(card_border_color(CardView.from_instance("counterspell_001", self.catalog)), "#63A8D5")
    self.assertEqual(card_border_color(CardView.from_instance("sol_ring_001", self.catalog)), "#AFB5B1")
```

- [ ] **Step 2: Run the test and confirm red.**

Run: `python -m unittest tests.test_gui_model.GuiModelTests.test_card_border_color_uses_catalog_colors -v`
Expected: import failure for `card_border_color`.

- [ ] **Step 3: Write a failing authoritative-resource test.**

```python
def test_resource_summary_counts_only_untapped_supported_mana_sources(self):
    view = GameView.from_state("p1", self._state_with_battlefield([
        {"card_id": "mountain_001", "tapped": False},
        {"card_id": "mountain_002", "tapped": True},
        {"card_id": "forest_001", "tapped": False},
        {"card_id": "sol_ring_001", "tapped": False},
        {"card_id": "goblin_guide_001", "tapped": False},
    ]), self.catalog)
    summary = resource_summary(view.player)
    self.assertEqual(summary.mana_sources, {"R": 1, "G": 1, "C": 2})
    self.assertEqual(summary.permanent_count, 5)
```

- [ ] **Step 4: Run it and confirm red.**

Run: `python -m unittest tests.test_gui_model.GuiModelTests.test_resource_summary_counts_only_untapped_supported_mana_sources -v`
Expected: import failure for `resource_summary`.

- [ ] **Step 4: Write the phase-neighbor regression test.**

```python
def test_phase_neighbors_use_the_protocol_phase_order(self):
    self.assertEqual(
        phase_neighbors("PRECOMBAT_MAIN"),
        ("DRAW", "PRECOMBAT_MAIN", "BEGIN_COMBAT"),
    )
```

- [ ] **Step 5: Run it and confirm red.**

Run: `python -m unittest tests.test_gui_model.GuiModelTests.test_phase_neighbors_use_the_protocol_phase_order -v`
Expected: import failure for `phase_neighbors`.

- [ ] **Step 6: Implement the minimal pure helpers.**

Use the card's `colors` tuple for the border. For empty colors return neutral; for more than one distinct color return gold. In `resource_summary`, ignore tapped permanents and count only the six exact supported base IDs listed in the locked decisions. Do not count Llanowar Elves or any rules text unless `GameEngine._validate_mana_payment` is expanded in a separate, server-authorized change. Derive `phase_neighbors` from the existing `PHASE_LABELS` insertion order and return the current phase unchanged in the middle position.

- [ ] **Step 7: Run the projection suite.**

Run: `python -m unittest tests.test_gui_model -v`
Expected: all pass.

## Task 2: Sprite-first fanned hand and resource-first right panel

**Files:**
- Modify: `client/gui.py`
- Modify: `tests/test_gui_smoke.py`

**Interfaces:**

```python
def GameApplication._render_hand(self, cards: tuple[CardView, ...]) -> None: ...
def GameApplication._render_resources(self, view: GameView) -> None: ...
def GameApplication._render_phase_strip(self, phase: str) -> None: ...
```

- [ ] **Step 1: Write failing Tk smoke tests.**

```python
def test_selected_hand_card_lifts_without_a_metadata_caption(self):
    app, store = self.make_connected_app()
    store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7, "state": self._state()})
    app._toggle_card("lightning_bolt_001")
    self.root.update_idletasks()
    self.assertEqual(app._focused_card_id, "lightning_bolt_001")
    self.assertGreater(app.hand_tiles["lightning_bolt_001"].winfo_y(), 0)
    self.assertFalse(any(child.cget("text").startswith("Mana:") for child in app.hand_tiles["lightning_bolt_001"].winfo_children() if isinstance(child, tk.Label)))

def test_resource_panel_shows_snapshot_counts_and_potential_mana(self):
    app, store = self.make_connected_app()
    store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7, "state": self._state_with_mountain()})
    self.root.update_idletasks()
    self.assertIn("20", app.resource_life_var.get())
    self.assertEqual(app.resource_mana_var.get(), "Potential mana: R 1")
```

- [ ] **Step 2: Run and confirm red.**

Run: `python -m unittest tests.test_gui_smoke.GuiSmokeTests.test_selected_hand_card_lifts_without_a_metadata_caption tests.test_gui_smoke.GuiSmokeTests.test_resource_panel_shows_snapshot_counts_and_potential_mana -v`
Expected: missing focused hand/resource state. If Tcl/Tk is unavailable, record the skip and rely on Task 1 pure tests until a Tcl/Tk-enabled Python is available.

- [ ] **Step 3: Implement the fanned hand.**

Use the existing horizontal canvas/scrollbar for the hand only. Render normal card sprites at approximately 144×201 pixels, place overlapping tiles at a fixed 104-pixel step, raise the focused tile enough to align the larger card's bottom edge with the row, and use an approximately 180×251-pixel cached image for it. At 8+ cards continue the same step inside the scroll region rather than compressing labels or creating a second row. After selection, call `canvas.xview_moveto` only as needed to keep the focused tile visible. Do not place type, mana, rules text, or another full card-detail panel around the sprite.

- [ ] **Step 4: Apply color outlines and selection semantics.**

Set every tile frame border from `card_border_color`. For selection, thicken that same semantic color ring and combine it with the raised/larger position; do not introduce a conflicting selection color. For tapped/summoning-sick/damaged cards, preserve explicit non-color state text only where it is not already visually represented by the sprite—never replace the semantic card-color outline.

- [ ] **Step 5: Render player status strips above their battlefields.**

Render compact, visibly labeled icon/value pairs in each battlefield's header: `Life`, `Hand`, `Library`, `Graveyard`, and `Exile`. In the player's header also show `Land played`, `Permanents`, and `Potential mana` pips. Render mana in `W, U, B, R, G, C` order and omit zero colors. Remove all duplicated player counts from the right panel; it must update on every authoritative state update.

- [ ] **Step 6: Replace the phase rail with the compact animated header strip.**

Delete `self.phase_rail` and its 14 `Label` widgets. Build a header `phase_strip` frame with three persistent labels: `previous_phase_var`, `phase_var`, and `next_phase_var`. Retain `self._displayed_phase`. On `view.phase` change, compare its index to the next protocol phase. For a consecutive change, use `place` plus `root.after(15, ...)` for ten frames across 150 ms; slide the three labels left, then reset their positions and set the new neighboring text. For any other change, update labels immediately. While movement occurs, `priority_var` and action rendering still update from the latest snapshot.

- [ ] **Step 7: Write and run a conditional phase-strip smoke test.**

```python
def test_phase_strip_exposes_previous_current_and_next(self):
    app, store = self.make_connected_app()
    store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7, "state": self._state()})
    self.root.update_idletasks()
    self.assertEqual(app.previous_phase_var.get(), "Draw")
    self.assertEqual(app.phase_var.get(), "Pre-combat main")
    self.assertEqual(app.next_phase_var.get(), "Begin combat")
```

Run: `python -m unittest tests.test_gui_smoke.GuiSmokeTests.test_phase_strip_exposes_previous_current_and_next -v`
Expected: failure until the phase strip exists; skip only if Tcl/Tk is unavailable.

- [ ] **Step 8: Run focused GUI tests.**

Run: `python -m unittest tests.test_gui_model tests.test_gui_actions tests.test_gui_smoke -v`.

## Task 3: Carry over the safety and resilience fixes

**Files:**
- Modify: `client/gui.py`
- Modify: `tests/test_gui_smoke.py`
- Modify: `tests/test_gui_actions.py`
- Modify: `README.md`

- [ ] Add and test idempotent disconnect recovery that closes the failed transport and restores the prefilled connection form.
- [ ] Add and test blocker dialogs with an explicit `Choose attacker…` placeholder; block submission while any selected blocker remains unset.
- [ ] Add documented keyboard behavior: Tab focus, Enter or Space to select a focused card, Escape to cancel all dialogs, Return to confirm target/blocker/damage-order dialogs, and Up/Down to move a damage-order entry.
- [ ] Bound `GuiEventBridge.drain(max_callbacks=32)` and activity history to 250 lines; add unit tests proving callbacks remain for the next tick and old log lines are removed.
- [ ] At width below 1180, stack controls below the board; no phase rail remains. Preserve vertical reachability and horizontal hand scrolling.
- [ ] Update the README to explain colored outlines, sprite-first cards, fanned hand selection, the three-label phase strip, `Potential mana`, keyboard controls, and reconnect.

## Final verification

- [x] `python -m compileall -q common server client tests scripts`
- [x] `python -m unittest discover -s tests -v` — 93 tests passed; 8 Tk smoke tests skipped because this Python installation cannot locate `init.tcl`.
- [ ] Manual two-client GUI check with Tcl/Tk available: 7-card and 15-card hand, colored outlines, selection lift, resource values after tapping/casting, disconnect/reconnect, blocker assignment, and compact window.
- [x] `git diff --check` and `git status --short`; report pre-existing user changes separately.
- [x] No staging, commit, or push without explicit authorization.
