---
name: design-tokens
description: Extract, normalize, or generate design tokens (colors, spacing, radii, typography, shadows) from CSS / Tailwind / SCSS / Figma exports into a single source of truth. Use when the user asks to unify colors, extract tokens, generate a token file, or audit inconsistent styling.
---

# design-tokens

Consolidate scattered style values into named tokens.

## Detection first

Glob for style sources:
- `**/*.css`, `**/*.scss`, `**/*.less`
- `tailwind.config.*`
- `**/*.stories.*`, Storybook `preview.*`
- `**/tokens*.json`, `**/design-tokens*`
- Inline `style={{...}}` in `**/*.{tsx,jsx,vue,svelte}`

Report: how many raw values (hex, rgb, px, rem) vs. token references. That number IS the debt.

## Extraction pass

Group raw values by likely semantic role:

| Bucket    | Detection heuristic                                    |
|-----------|--------------------------------------------------------|
| color     | hex / rgb / hsl / oklch                                |
| spacing   | px / rem values used in padding, margin, gap          |
| radius    | border-radius                                          |
| typography| font-family, font-size, line-height, letter-spacing   |
| shadow    | box-shadow                                             |
| motion    | transition, animation duration/easing                  |

Cluster near-duplicates (`#0a0a0a`, `#0b0b0b`, `#111` → one token). Rank by frequency. Propose names.

## Output format

Default to **W3C DTCG** (`$value` + `$type`) unless the project already uses another format:

```json
{
  "color": {
    "surface": {
      "base": { "$value": "#ffffff", "$type": "color" },
      "muted": { "$value": "#f6f7f9", "$type": "color" }
    }
  },
  "space": {
    "1": { "$value": "0.25rem", "$type": "dimension" }
  }
}
```

Then generate the project-specific mirror:
- Tailwind → `theme.extend` entries in `tailwind.config.*`.
- CSS → `:root { --color-surface-base: … }` block with dark-mode override.
- SCSS → `$color-surface-base: …` variables + a map.

## Rewrite pass (only on request)

Ask before touching source files. If yes:
- Replace raw values with token references, one file at a time.
- Show diff per file.
- Preserve any value the token doesn't cover (flag as "unresolved").

## Hard rules

- Never invent tokens for values that appear once — that is a raw value, not a token.
- Never merge colors across dark/light without confirming they truly pair.
- Never change visible output during extraction — token names are new; values are copied exactly.
