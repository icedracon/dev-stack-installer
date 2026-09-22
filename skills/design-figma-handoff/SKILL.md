---
name: design-figma-handoff
description: Turn a Figma frame (link or exported JSON) into a component spec a developer can ship — semantic tokens, states, a11y notes, and a scaffold in the project's UI framework. Use when the user shares a Figma URL, asks to implement a design, or says "convert this frame to code".
---

# design-figma-handoff

Bridge from design file to production component. Do not translate pixel-for-pixel — extract intent.

## Inputs accepted

- Figma share URL (needs figma MCP OR user pastes exported JSON / dev-mode CSS).
- Screenshot + brief spec text.
- Design token export (Style Dictionary, W3C DTCG JSON).

## Output shape (per component)

```
COMPONENT: <name>
INTENT:    <one line — what user need it serves>
VARIANTS:  <primary/secondary/…> × <sm/md/lg> × <default/hover/active/disabled/loading/error>
TOKENS:    - color:  bg=<token>, fg=<token>, border=<token>
           - space:  padding=<token>, gap=<token>
           - radius: <token>
           - type:   <token>
A11Y:      - role, aria-*, keyboard, focus ring, min touch target
STATES:    concrete rules per state (not "hover state has a color change")
SCAFFOLD:  ready-to-paste file in the project's framework
```

## Framework detection (before scaffolding)

Look at `package.json` / `Cargo.toml` / etc.:
- `next` + `tailwindcss` → RSC-friendly component in `app/_components/` or the project's existing convention.
- `react` + CSS modules → `.module.css` sibling.
- `vue` → SFC.
- `svelte` → `.svelte`.
- `angular` → `component.ts + .html + .scss` trio.
- No framework detected → **ask** before scaffolding.

Copy the project's existing component pattern (naming, exports, prop style). Never introduce a new library.

## Token discipline

- Prefer semantic tokens (`--color-surface`) over primitive (`--gray-100`).
- If the project has `tailwind.config.*` with a theme, use those keys.
- If tokens are missing, emit a `design-tokens.md` proposal file (do not write to the config without asking).

## A11y checklist (always run)

- Interactive elements have discernible name.
- Color contrast ≥ 4.5:1 body / 3:1 large.
- Keyboard focus visible and moves logically.
- Non-decorative images have `alt`.
- Motion respects `prefers-reduced-motion`.

## Anti-patterns

- Do not translate absolute-positioned auto-layout to `position: absolute` — use flex/grid.
- Do not hardcode hex — always token-first.
- Do not scaffold a design system if the project already has one.
