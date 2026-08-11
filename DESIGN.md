---
name: MTGNP Quiet Tabletop
description: A dark, calm tabletop control surface for the server-authoritative two-player MTGNP client.
colors:
  background: "#101617"
  activity-well: "#121819"
  surface: "#182021"
  surface-raised: "#202a2b"
  felt: "#24302f"
  border: "#3a4847"
  text: "#eee8dc"
  muted: "#b8c1bd"
  faint: "#899591"
  accent: "#78c9be"
  accent-dark: "#31554f"
  warm: "#d8bd88"
  danger: "#d99986"
  input-paper: "#f4f1e8"
  accent-ink: "#f5fffd"
  danger-deep: "#5a3732"
  danger-ink: "#ffe9e2"
  button-neutral: "#303b3b"
  button-neutral-hover: "#3b4847"
  button-neutral-disabled: "#252d2d"
  card-active: "#354140"
  stack-border: "#586765"
  hand-border: "#655b43"
  mana-white: "#F3DF9B"
  mana-blue: "#63A8D5"
  mana-black: "#997AAF"
  mana-red: "#D76A5B"
  mana-green: "#63AA73"
  mana-colorless: "#AFB5B1"
  card-multicolor: "#D5AD49"
typography:
  display:
    fontFamily: "Georgia, serif"
    fontSize: "23pt"
    fontWeight: 700
  headline:
    fontFamily: "Georgia, serif"
    fontSize: "12pt"
    fontWeight: 700
  body:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "10pt"
    fontWeight: 400
  body-compact:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "9pt"
    fontWeight: 400
  label:
    fontFamily: "Segoe UI Semibold, Segoe UI, sans-serif"
    fontSize: "9pt"
    fontWeight: 600
  metadata:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "8pt"
    fontWeight: 400
spacing:
  micro: "3px"
  xs: "5px"
  sm: "8px"
  md: "10px"
  lg: "12px"
  xl: "16px"
  dialog: "18px"
  connection-shell: "36px"
components:
  button-primary:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.label}"
    padding: "10px 14px"
  button-primary-hover:
    backgroundColor: "#416f67"
  button-secondary:
    backgroundColor: "{colors.button-neutral}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    padding: "9px 12px"
  button-danger:
    backgroundColor: "{colors.danger-deep}"
    textColor: "{colors.danger-ink}"
    typography: "{typography.label}"
    padding: "9px 12px"
  input:
    backgroundColor: "{colors.input-paper}"
    textColor: "{colors.surface}"
    typography: "{typography.body}"
    padding: "8px"
  card-zone:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text}"
    height: "232px"
  hand-zone:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    height: "276px"
---

# Design System: MTGNP Quiet Tabletop

## Overview

**Creative North Star: "The Quiet Tabletop"**

The client is a focused tabletop control surface: dark, calm, readable, and lightly tactile. Charcoal framing and green-black felt establish the play surface, warm parchment headings provide restrained ceremony, and teal marks priority, direction, and actionable state. The visual system keeps attention on the server-authoritative game state rather than ornamental fantasy chrome.

The interface follows the match itself: connect, scan both players' resources at their battlefields, follow the current phase and priority, select cards, act through the protocol, and read the authoritative response. Real card frames and color-semantic outlines carry card identity; the surrounding application remains quiet and functional.

**Key Characteristics:**

- Dark charcoal and felt surfaces with flat tonal separation.
- Warm Georgia headings paired with compact Segoe UI controls and metadata.
- Restrained teal for priority, flow arrows, icons, and primary actions.
- Card-color outlines and mana pips that supplement, never replace, text and position.
- Responsive stacking, bounded scrolling, a brief phase-flow animation, and restrained hand-card hover feedback.

## Colors

The palette is a low-luminance tabletop field with parchment text, a cool teal interaction cue, a muted rose danger family, and the six familiar mana/card identities.

### Primary

- **Priority Teal:** Marks priority status, phase arrows, resource icons, and primary-action surfaces.
- **Deep Priority Teal:** Grounds primary buttons and text selection without becoming luminous chrome.

### Secondary

- **Parchment Gold:** Identifies the MTGNP title, current phase, player identities, and section headings.
- **Quiet Rose:** Reports card damage, validation failures, and destructive intent without using a saturated alarm red.

### Tertiary

- **Mana White, Blue, Black, Red, Green, and Colorless:** Color the potential-mana pips and the semantic outline of single-color or colorless cards.
- **Multicolor Gold:** Outlines cards whose catalog identity contains more than one color.

### Neutral

- **Table Void:** Frames the application and separates the game shell from the desktop.
- **Activity Well:** Recedes the history log and list controls within their containing surface.
- **Charcoal Surface:** Forms headers, side panels, dialogs, and hand/stack containers.
- **Raised Charcoal:** Distinguishes cards and stack items from their parent surface.
- **Green-Black Felt:** Holds both battlefields and their resource strips.
- **Quiet Border:** Provides the standard one-pixel structural outline.
- **Parchment Text:** Carries primary readable content; muted and faint sage-gray steps carry secondary and tertiary information.
- **Paper Input:** Gives editable fields an unmistakable light writing surface with dark ink.

### Named Rules

**The Teal Means Agency Rule.** Reserve teal for priority, flow, resource cues, and primary actions; it is not a decorative wash.

**The Card Identity Rule.** Use the catalog-derived W/U/B/R/G, colorless, or multicolor outline for cards, while retaining text, focus, and position cues so color never acts alone.

## Typography

**Display Font:** Georgia (with the platform serif fallback)

**Body Font:** Segoe UI (with the platform sans-serif fallback)

**Label Font:** Segoe UI Semibold (with Segoe UI fallback)

**Character:** Georgia supplies a small amount of tabletop gravitas for identity and hierarchy. Segoe UI keeps controls, game state, metadata, and activity text native, compact, and easy to scan on Windows.

### Hierarchy

- **Display** (bold, 23pt): The MTGNP mark on connection and game screens.
- **Headline** (bold, 12pt): Section names, player identities, and the current phase.
- **Body** (regular, 10pt): Labels, prompts, lists, and general interface copy.
- **Compact body** (regular, 9pt): Adjacent phases, activity history, empty states, and compact supporting text.
- **Label** (semibold, 9pt): Button labels and status emphasis.
- **Metadata** (regular or semibold, 8pt): Resource names and values, mana pips, battlefield captions, and card status.

### Named Rules

**The Two-Voice Rule.** Georgia speaks only for identity and hierarchy; Segoe UI carries operations and state.

## Layout

The default window opens at 1400 by 900 pixels and never shrinks below 760 by 600. The game shell uses 16-pixel horizontal margins, a 12-pixel top inset, and a 14-pixel bottom inset. A full-width status header sits above the main content, followed by the felt board and a fixed 285-pixel action/activity panel on the right.

The match uses a single fixed composition at a minimum 1180-by-860 window: the board and action/activity panel remain side by side, with no whole-window scrolling. Compact battlefield previews preserve vertical room for the large hand. Every card row retains independent mouse-wheel scrolling without exposing a scrollbar track.

Within the board, the order is opponent resources, opponent battlefield, stack, player resources, player battlefield, then the anchored hand. Resource strips remain adjacent to their respective battlefield instead of moving into a detached dashboard. The connection screen centers a single bordered panel with 36-pixel shell padding and 34-by-30-pixel internal padding.

**The Adjacent State Rule.** Put each player's public resources directly beside that player's battlefield so evaluation does not require cross-screen searching.

## Elevation & Depth

This is a flat tonal system with no shadows. Depth comes from nested charcoal/felt values, one-pixel outlines, raised card surfaces, and local selection thickness. The stack and hand use slightly warmer or cooler semantic border variants while remaining on the same physical plane.

**The Flat Table Rule.** Do not introduce drop shadows, gloss, glass, or ornamental bevels; distinguish layers with tone, border, and spacing.

## Shapes

The interface chrome remains square and mechanically quiet. Cards are the deliberate exception: cached Tk images composite a 14-pixel rounded semantic edge around the supplied transparent artwork, while the underlying native button remains responsible for input. Unselected cards receive a two-pixel edge, hovered hand cards use four pixels, and selected cards use six pixels.

Resource symbols and mana pips are the deliberate exceptions: 13-pixel canvas glyphs use simple circles, rectangles, polygons, and lines, while mana values sit in compact filled rectangular pips.

## Components

### Buttons

- **Shape:** Flat, square controls with no visible border or radius.
- **Primary:** Deep teal with near-white teal ink and 14-by-10-pixel padding; used for the current recommended protocol action such as connect, keep hand, pass priority, or confirm.
- **Primary hover:** Shifts to a lighter muted teal. Keyboard focus remains the native ttk focus affordance.
- **Secondary:** Neutral charcoal with parchment text and 12-by-9-pixel padding; hover lightens one tonal step and disabled controls darken while text becomes faint.
- **Danger:** Deep muted brown-red with pale rose text; reserved for conceding the match.

### Cards / Containers

- **Battlefield cards:** Real local card frames are displayed as compact 90-pixel-wide previews when available; a text fallback remains usable when artwork cannot load. Rounded outline images sit on native buttons, so click and keyboard behavior do not depend on canvas item bindings. Battlefield strips stay in a straight horizontal row and scroll with the wheel without visible scrollbar chrome.
- **Hand cards:** The hand occupies a 322-pixel-high, four-position viewport. Cards overlap on a 132-pixel step. Resting cards begin 62 pixels from the top at approximately 180 pixels wide; hover previews rise to 28 pixels and grow to approximately 200 pixels over 90 milliseconds; selected cards rise to 4 pixels and remain approximately 216 pixels wide. The mouse wheel navigates the row directly, without buttons or visible scrollbar chrome.
- **Selection and state:** Hover is temporary; selection persists. Both use the card's semantic color, increased border thickness, raised position, and larger art. Tapped, damage, and summoning-sick state appears beneath battlefield cards in quiet rose.
- **Containers:** The header, side panel, connection panel, board, stack, hand, and dialogs use flat tonal layers with one-pixel outlines where structure needs definition.

### Inputs / Fields

- **Text entry:** A light paper field with dark charcoal ink and 8-pixel internal padding makes editable connection data distinct from read-only game state.
- **Choice controls:** Read-only comboboxes and the dark ordering list use the same compact operational typography. Selection uses deep teal.
- **Activity log:** A borderless dark well with muted text, 8-pixel internal padding, word wrapping, and a bounded 250-entry history.
- **Error / disabled:** Validation copy uses quiet rose. Disabled buttons use the disabled charcoal and faint text tokens.

### Dialogs

Choice, ordering, and blocker-assignment dialogs are modal child windows on the charcoal surface. They use 18-pixel edge spacing, a warm Georgia prompt, compact native choice controls, and a full-width primary confirmation action. Enter confirms, Escape cancels, and the first decision control receives focus.

### Resource Strips

Each battlefield begins with a player identity and compact resource metrics. Teal 13-pixel line icons precede faint labels and semibold values. The player's strip uses up to four metrics per row and adds potential-mana pips; the opponent's five public metrics occupy one row.

### Phase Flow

The 410-by-34-pixel phase strip shows the previous phase, current phase, and next phase connected by teal arrows. Adjacent phases use faint 9pt Segoe UI; the current phase uses warm bold 12pt Georgia. Consecutive phase changes slide the strip left across 136 pixels in ten linear 15-millisecond frames. Initial, repeated, nonconsecutive, or lifecycle-changing updates render immediately.

### Stack and Actions

The stack is a bordered horizontal sequence with the newest item presented first and each spell/effect rendered as a raised tonal label. The right panel derives its vertically stacked actions from the protocol state and current selection; when no action is available, it explains whether the client is waiting or needs a selection.

## Do's and Don'ts

### Do:

- **Do** preserve the charcoal, felt, parchment, teal, and semantic card-color roles exactly.
- **Do** keep public resources adjacent to their battlefield and the contextual actions beside or immediately below the board.
- **Do** keep battlefield cards in straight strips and reserve overlap, hover lift, enlargement, and bounded navigation for the player's hand.
- **Do** retain text, focus, size, and position cues alongside semantic color.
- **Do** keep the 1180-pixel responsive transition and both axes of overflow usable down to the 760-by-600 minimum window.
- **Do** limit motion to the 150-millisecond consecutive-phase slide and 90-millisecond hand-card lift; both transitions explain state and remain interruptible.

### Don't:

- **Don't** add ornamental fantasy chrome, gradients, glass effects, drop shadows, or decorative texture.
- **Don't** add a redundant full phase rail; preserve the flowing previous-current-next phase strip.
- **Don't** detach resources into a remote dashboard or move game authority into the presentation layer.
- **Don't** replace native card buttons with canvas-only hit targets; composite the rounded image separately and preserve the proven input path.
- **Don't** rely on color alone for card identity, selection, focus, damage, or disabled state.
- **Don't** introduce web-only navigation, chips, hover-dependent actions, or browser layout claims into this Tkinter desktop system.
