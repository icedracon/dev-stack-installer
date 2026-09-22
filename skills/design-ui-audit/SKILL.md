---
name: design-ui-audit
description: Audit a live page or component tree for accessibility, visual consistency, responsive behavior, and dark-mode parity. Use when the user asks to audit UI, check a11y, verify responsive design, or review a page before ship.
---

# design-ui-audit

Two-pass audit: source pass (fast, static) + browser pass (evidence).

## Pass 1 — source

Grep for known smells:

- `alt=""` on non-decorative `<img>`; missing `alt` entirely.
- `<div onClick>` / `<span onClick>` without role + keyboard handler.
- Color mentioned inline (hex/rgb) inside components — points to token debt (delegate to [[design-tokens]]).
- Hard-coded px in `width`/`height` on containers that should be fluid.
- `outline: none` without a replacement focus style.
- `role="button"` without `tabindex="0"` and Enter/Space handling.
- Text under 14px in body content.
- Missing `<label for>` / `aria-label` on form inputs.
- `<h1>` count ≠ 1 per route; heading levels skipping.

Emit findings with `file:line`.

## Pass 2 — browser (if browser tool available)

Use built-in browser preview:

1. Start dev server (`preview_start` with the project's launch config).
2. For each key route:
   - `read_page` → check landmarks (`main`, `nav`, `header`, `footer`) exist.
   - Screenshot at 320 / 768 / 1280 / 1920 widths.
   - Toggle `colorScheme: dark` → screenshot again.
   - `read_console_messages` → any errors?
3. For interactive components: tab through with `computer key=Tab`, verify focus order and visible focus ring in a screenshot.
4. Zoom to 200%; check nothing is cut off or overlapping.

## Report format

```
UI AUDIT — <route>

BLOCKING (ship-stopper)
- <finding> — file:line — evidence: <screenshot ref or console line>

HIGH
- ...

CLEANUP
- ...

METRICS
- viewport parity 320/768/1280/1920: pass / fail per bp
- dark parity: pass / fail
- console errors: N
```

## What this skill does NOT do

- Automated Lighthouse (delegate to [[code-perf-budget]]).
- Screen-reader testing (must be manual — flag it, don't fake it).
- Design opinions on layout / hierarchy (a11y + parity only).
