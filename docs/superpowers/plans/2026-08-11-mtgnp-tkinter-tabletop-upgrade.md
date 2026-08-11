# MTGNP Tkinter Tabletop Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Tkinter client so cards show readable name/mana/state captions, the hand is a selected-card fan with an in-context detail panel, and the review's recovery, keyboard, combat-safety, and layout issues are resolved.

**Architecture:** Keep `ClientNetwork`, `ClientStateStore`, and `ClientController` presentation-neutral and server-authoritative. Put deterministic card-caption and hand-layout calculations in `client.gui_model`, then keep `GameApplication` responsible only for Tk widget creation, event bindings, session transitions, and rendering those pure projections. Continue using `GuiEventBridge` to move network callbacks to Tk's main thread.

**Tech Stack:** Python 3.12; standard-library Tkinter/ttk; unittest; existing local PNG card assets; no third-party packages.

## Global Constraints

- Do not add runtime dependencies, runtime web requests, or client-side rules decisions.
- Preserve `client/gui.py`'s existing uncommitted mana/type caption work; integrate it rather than reverting or overwriting it.
- Keep terminal-client behavior and all controller/PDU contracts unchanged.
- Maintain private-information boundaries: opponent hand stays a count only.
- Do not stage, commit, or push this handoff work unless the repository owner explicitly authorizes it.
- Run the implementation in an isolated worktree only after approval; do not create one while producing this plan.

---

## File map

| File | Responsibility |
|---|---|
| `client/gui_model.py` | Pure card caption, selected-detail, fan geometry, and bounded bridge helpers. |
| `client/gui.py` | Tk rendering: fanned hand, selected-card panel, keyboard/dialog behavior, responsive shell, and connection recovery. |
| `tests/test_gui_model.py` | Fast tests for captions, detail projections, fan positions, and bounded event draining. |
| `tests/test_gui_smoke.py` | Conditional Tcl/Tk rendering tests for selected-card behavior, caption widgets, blocker safeguards, and disconnect recovery. |
| `tests/test_gui_actions.py` | Dispatch regression tests; retain PDU payload behavior unchanged. |
| `README.md` | Short desktop-client interaction help for selection, inspection, and reconnect. |

## Task 1: Add testable card presentation and fan-layout helpers

**Files:**
- Modify: `client/gui_model.py:81-301`
- Modify: `tests/test_gui_model.py:1-143`

**Interfaces:**
- Produces `format_mana_cost(mana_cost: Mapping[str, int]) -> str`.
- Produces `CardDisplay` with `name`, `facts`, `status`, `rules_text`, and `selected_summary` fields.
- Produces `card_display(card: CardView) -> CardDisplay`.
- Produces `HandCardLayout(left: int, top: int, image_size: str, z_index: int)` and `fan_hand_layout(card_ids: Sequence[str], focused_id: str | None) -> dict[str, HandCardLayout]`.
- Changes `GuiEventBridge.drain` to accept `max_callbacks: int | None = None` and return after that many callbacks.

- [ ] **Step 1: Write failing tests for card captions and selected detail.**

```python
def test_card_display_exposes_name_mana_type_and_creature_stats(self):
    card = CardView.from_instance("lightning_bolt_001", self.catalog)
    display = card_display(card)
    self.assertEqual(display.name, "Lightning Bolt")
    self.assertEqual(display.facts, "Mana: R · Instant")

    creature = CardView.from_instance(
        "goblin_guide_001", self.catalog,
        {"card_id": "goblin_guide_001", "power_modifier": 1, "toughness_modifier": 0},
    )
    self.assertEqual(card_display(creature).facts, "Mana: R · Creature · 3/2")

def test_card_display_marks_costless_cards_and_explicit_statuses(self):
    land = CardView.from_instance("mountain_001", self.catalog)
    self.assertEqual(card_display(land).facts, "Mana: — · Land")

    tapped = CardView.from_instance(
        "mountain_001", self.catalog,
        {"card_id": "mountain_001", "tapped": True, "damage": 2, "summoning_sick": True},
    )
    self.assertEqual(card_display(tapped).status, "Tapped · 2 damage · Summoning sick")
```

- [ ] **Step 2: Run the focused tests and confirm they fail because the presentation helpers do not exist.**

Run: `python -m unittest tests.test_gui_model.GuiModelTests.test_card_display_exposes_name_mana_type_and_creature_stats tests.test_gui_model.GuiModelTests.test_card_display_marks_costless_cards_and_explicit_statuses -v`
Expected: import/attribute failure for `card_display`.

- [ ] **Step 3: Write failing tests for deterministic fan geometry and bounded event draining.**

```python
def test_fan_hand_layout_raises_and_enlarges_the_focused_card(self):
    layout = fan_hand_layout(["a", "b", "c"], "b")
    self.assertLess(layout["b"].top, layout["a"].top)
    self.assertEqual(layout["b"].image_size, "hand_selected")
    self.assertEqual(layout["b"].z_index, 3)
    self.assertEqual(layout["a"].image_size, "hand")

def test_event_bridge_can_drain_a_bounded_batch(self):
    bridge = GuiEventBridge()
    received = []
    for item in range(3):
        bridge.post(received.append, item)
    self.assertEqual(bridge.drain(max_callbacks=2), 2)
    self.assertEqual(received, [0, 1])
    self.assertEqual(bridge.drain(max_callbacks=2), 1)
```

- [ ] **Step 4: Run the focused tests and confirm they fail for the missing layout/bounded-drain behavior.**

Run: `python -m unittest tests.test_gui_model.GuiModelTests.test_fan_hand_layout_raises_and_enlarges_the_focused_card tests.test_gui_model.GuiModelTests.test_event_bridge_can_drain_a_bounded_batch -v`
Expected: import/attribute failure for `fan_hand_layout` or the unexpected `max_callbacks` argument.

- [ ] **Step 5: Implement the minimal pure helpers.**

```python
@dataclass(frozen=True)
class HandCardLayout:
    left: int
    top: int
    image_size: str
    z_index: int

def fan_hand_layout(card_ids, focused_id):
    return {
        card_id: HandCardLayout(
            left=index * 46,
            top=18 + abs((len(card_ids) - 1) / 2 - index) * 5 - (18 if card_id == focused_id else 0),
            image_size="hand_selected" if card_id == focused_id else "hand",
            z_index=len(card_ids) if card_id == focused_id else index,
        )
        for index, card_id in enumerate(card_ids)
    }
```

Keep formatting order `generic`, then `WUBRG`; use `—` only for an empty cost. Keep status text literal and non-emoji so it is reliably readable.

- [ ] **Step 6: Run the full projection suite.**

Run: `python -m unittest tests.test_gui_model -v`
Expected: all tests pass.

## Task 2: Render the readable fanned hand and selected-card detail panel

**Files:**
- Modify: `client/gui.py:247-668`
- Modify: `tests/test_gui_smoke.py:27-122`

**Interfaces:**
- Consumes `card_display` and `fan_hand_layout` from `client.gui_model`.
- Adds `GameApplication._focused_card_id: str | None`.
- Adds `GameApplication._render_hand(cards: tuple[CardView, ...]) -> None`.
- Adds `GameApplication._render_selected_card(view: GameView) -> None`.
- Extends `_card_image` sizes to `hand` (80×~112), `hand_selected` (120×~167), and existing `full`.

- [ ] **Step 1: Write a conditional Tk smoke test for card captions and selection detail.**

```python
def test_selected_hand_card_shows_name_mana_and_details(self):
    app, store = self.make_connected_app()
    store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7, "state": self._state()})
    app._toggle_card("lightning_bolt_001")
    self.root.update_idletasks()
    self.assertEqual(app.selected_name_var.get(), "Lightning Bolt")
    self.assertEqual(app.selected_facts_var.get(), "Mana: R · Instant")
    self.assertIn("3 damage", app.selected_rules_var.get())
    self.assertEqual(app._focused_card_id, "lightning_bolt_001")
```

- [ ] **Step 2: Run it and confirm it fails because the selected-card variables/focused state do not exist.**

Run: `python -m unittest tests.test_gui_smoke.GuiSmokeTests.test_selected_hand_card_shows_name_mana_and_details -v`
Expected: failure for missing selected-card state. If Tcl/Tk is unavailable, record the skip and run the Task 1 pure suite as the executable fallback.

- [ ] **Step 3: Replace only the hand strip with a fan renderer.**

Create a `Canvas` plus an inner frame for the hand, call `fan_hand_layout` for positions, and place each tile at its calculated `left/top`. Configure an inner width of `max(canvas_width, 46 * (len(cards) - 1) + 136)` and a fixed content height that accommodates the raised selected tile. Keep the existing horizontal scrollbar. Do not rotate images: Tk's standard `PhotoImage` cannot rotate them without adding a dependency.

Render caption labels beneath every image in this exact hierarchy:

```text
Lightning Bolt
Mana: R · Instant
Tapped · 2 damage · Summoning sick
```

The status row remains present but empty when there is no state, keeping tile rhythm stable. Battlefield/opponent strips use the same caption component but retain their straight layout.

- [ ] **Step 4: Add selected-card detail to the right panel.**

Place a `Selected card` section between selection status and `Available actions`. Use `StringVar`s for name, facts, and rules text. For no focused card show `Select a card to view its details.` For a selected card show name, mana/type/stats, keywords/status, rules text, and an `Inspect selected card` button. The button and double-click both call `_show_card_detail`; bind Enter on a focused card to the same method.

- [ ] **Step 5: Preserve multi-selection correctly.**

In `_toggle_card`, set `_focused_card_id` to the last selected card. On deselection, use the most recently remaining selected ID when one exists; clear it otherwise. In `_render_state`, clear focus only if it is no longer visible. Action dispatch must continue receiving all selected IDs, not just the focused card.

- [ ] **Step 6: Run focused GUI tests.**

Run: `python -m unittest tests.test_gui_smoke tests.test_gui_actions tests.test_gui_model -v`
Expected: all non-Tk tests pass; smoke tests pass when Tcl/Tk is installed or are explicitly skipped only for missing Tcl/Tk.

## Task 3: Add safe keyboard/dialog behavior and disconnect recovery

**Files:**
- Modify: `client/gui.py:183-232, 670-905`
- Modify: `tests/test_gui_smoke.py:13-122`
- Modify: `tests/test_gui_actions.py:16-106`

**Interfaces:**
- Adds `GameApplication._return_to_connection(message: str) -> None`.
- Adds `GameApplication._connection_defaults() -> tuple[str, int, str, str]`.
- Adds `GameApplication._set_game_controls_enabled(enabled: bool) -> None`.
- Changes `_choose_blocker_map` to require an explicit attacker for every selected blocker.

- [ ] **Step 1: Write a conditional smoke test for in-game disconnect recovery.**

```python
class RecordingNetwork:
    def __init__(self):
        self.closed = False
    def close(self):
        self.closed = True

def test_disconnect_returns_to_prefilled_connection_screen(self):
    network = RecordingNetwork()
    app = self.make_connected_app(network=network, deck_list=["mountain_001"])
    app._connection_failed(ConnectionError("server closed"))
    self.root.update_idletasks()
    self.assertTrue(network.closed)
    self.assertIsNone(app.controller)
    self.assertEqual(app.host_var.get(), "127.0.0.1")
    self.assertEqual(app.deck_var.get(), "decks/red.json")
    self.assertIn("server closed", app.status_var.get())
```

- [ ] **Step 2: Run it and confirm it fails because the disconnected game screen is currently retained.**

Run: `python -m unittest tests.test_gui_smoke.GuiSmokeTests.test_disconnect_returns_to_prefilled_connection_screen -v`
Expected: assertion failure: network not closed, controller remains present, or connection fields are absent.

- [ ] **Step 3: Implement idempotent disconnect recovery.**

Store the latest connection defaults before session replacement. In `_connection_failed`, distinguish a connection-form failure from an active-session failure. For active sessions: close the current network once; set `network`, `controller`, and `store` to `None`; clear selection/focus; rebuild the connection screen with saved values; set a recovery message; and never call widgets that belonged to the destroyed game screen.

- [ ] **Step 4: Write and run the blocker-default regression test.**

```python
def test_blocker_dialog_requires_a_choice_for_each_blocker(self):
    app, _store = self.make_connected_app()
    dialog_state = app._blocker_choice_state(["blocker_a"], ["attacker_a", "attacker_b"])
    self.assertEqual(dialog_state["blocker_a"], "")
```

Run: `python -m unittest tests.test_gui_smoke.GuiSmokeTests.test_blocker_dialog_requires_a_choice_for_each_blocker -v`
Expected: failure for the missing helper or the existing first-attacker default.

- [ ] **Step 5: Implement safe blocker choices and complete keyboard paths.**

Use a stable `""` value labeled `Choose attacker…`; only enable `Declare blockers` when no choice is empty. Bind Return to accept dialogs, Escape and `WM_DELETE_WINDOW` to cancel, set initial focus, and bind Up/Down movement for the damage-order list. Bind `p` to pass priority only when the contextual pass action is legal, and show `P — Pass priority` in its button label. Ensure buttons retain standard Tab navigation and focus visibility.

- [ ] **Step 6: Run action and smoke tests.**

Run: `python -m unittest tests.test_gui_actions tests.test_gui_smoke -v`
Expected: dispatch PDU payloads remain unchanged; smoke tests pass with Tcl/Tk or skip only because Tcl/Tk is absent.

## Task 4: Make the shell resilient under dense state and compact windows

**Files:**
- Modify: `client/gui.py:247-371, 378-515, 850-893`
- Modify: `tests/test_gui_model.py:50-74`
- Modify: `tests/test_gui_smoke.py:27-122`
- Modify: `README.md:12-33`

**Interfaces:**
- Uses `GuiEventBridge.drain(max_callbacks=32)` from Task 1.
- Adds `GameApplication._append_log` trimming to `MAX_ACTIVITY_LINES = 250`.
- Adds `GameApplication._update_compact_layout(width: int) -> None` bound to the root/shell configure event.

- [ ] **Step 1: Write a pure bridge regression test for a long queue.**

```python
def test_event_bridge_leaves_remaining_callbacks_for_the_next_tick(self):
    bridge = GuiEventBridge()
    received = []
    for item in range(33):
        bridge.post(received.append, item)
    self.assertEqual(bridge.drain(max_callbacks=32), 32)
    self.assertEqual(received[-1], 31)
    self.assertEqual(bridge.drain(max_callbacks=32), 1)
```

- [ ] **Step 2: Run it and confirm it fails until bounded draining exists.**

Run: `python -m unittest tests.test_gui_model.GuiModelTests.test_event_bridge_leaves_remaining_callbacks_for_the_next_tick -v`
Expected: the original unbounded implementation drains all 33 callbacks.

- [ ] **Step 3: Implement responsive and bounded behavior.**

At shell width below 1180, hide non-active phase labels behind three labeled groups (`Beginning`, `Combat`, `Ending`) and stack the action panel below the board; above 1180 retain the current three-column layout. Give the main content a vertical canvas/scrollbar so the action panel is reachable at minimum height. Preserve the existing horizontal strip scrollbars. In `_drain_bridge`, request 32 callbacks per 40 ms tick. In `_append_log`, trim oldest lines after 250 entries before adding the next message.

- [ ] **Step 4: Write a conditional smoke test for compact layout state.**

```python
def test_compact_layout_keeps_action_panel_managed(self):
    app, _store = self.make_connected_app()
    app._update_compact_layout(1100)
    self.assertTrue(app.compact_layout)
    self.assertTrue(app.action_container.winfo_manager())
```

- [ ] **Step 5: Run the focused verification set.**

Run: `python -m unittest tests.test_gui_model tests.test_gui_actions tests.test_gui_smoke -v`
Expected: projection/action tests pass; Tk smoke tests pass where Tcl/Tk is available.

- [ ] **Step 6: Document the interaction contract.**

Add a short README subsection after desktop launch instructions:

```markdown
### Desktop controls

- Click cards to select them; selected hand cards lift above the fan and show details in the right panel.
- Press Enter or double-click a focused card to inspect its full text.
- Press `P` when the Pass priority control is available.
- After a disconnect, use the restored connection form to retry with the same settings.
```

## Final verification and handoff

- [ ] Run `python -m compileall -q common server client tests scripts`.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] On a Python installation with Tcl/Tk enabled, start one server and two GUI clients using the README commands; inspect connection, mulligan, the fanned hand, selection/inspection, targeting, blockers, disconnect recovery, and restart.
- [ ] Run `git diff --check` and `git status --short`; confirm only intended files changed and the pre-existing uncommitted GUI work was preserved/integrated.
- [ ] Do not stage, commit, or push without explicit repository-owner approval.

## Plan self-review

- Coverage: Tasks 1-2 implement readable name/mana captions, fanned selected hand, and selected detail. Task 3 implements reconnect, keyboard, dialog, and blocker-safety findings. Task 4 implements compact layout, bounded updates/log, documentation, and full verification.
- Consistency: `CardDisplay`, `fan_hand_layout`, and bounded bridge APIs are introduced in Task 1 before Tasks 2 and 4 consume them.
- Scope: no server protocol, card rules, terminal UI, dependencies, or image downloads change.
