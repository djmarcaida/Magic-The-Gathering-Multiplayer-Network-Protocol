# MTGNP Client GUI

## Product

A lightweight desktop interface for the existing Python MTGNP client. It lets one of exactly two networked players connect, complete setup and mulligan, play through turn phases, respond to stack priority, and see the server-authoritative game state.

## Audience

Students and evaluators running the protocol project locally on ordinary Windows machines. The interface should make the networking and game-state flow easy to demonstrate without requiring command-line fluency.

## Core experience

- Connect to a server with a player ID and one of the supplied decks.
- See both players' public state, the battlefield, stack, phases, priority, hand, and activity history at a glance.
- Perform only actions supported by the existing protocol and supplied card catalog.
- Receive an updated authoritative state after each request.
- Keep all rule decisions on the server; the GUI only presents state and sends actions.

## Platform

Desktop Python application, designed first for Windows and kept portable through the standard-library Tkinter/ttk toolkit.

## Visual character

Focused tabletop control surface: dark, calm, readable, and lightly tactile. Use card color/type cues and restrained metallic accents without relying on external artwork or assets.

## Constraints

- No production dependency is required beyond Python's standard library.
- Use only the provided specifications, Prompt.pdf, and `cards.json` as content sources.
- Preserve the terminal client and the existing network/controller/state-store boundaries.
- Favor clear interactions and reliable resizing over animation or decorative complexity.
