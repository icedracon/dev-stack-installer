---
name: code-perf-budget
description: Set and enforce frontend performance budgets — bundle size, Lighthouse scores, Core Web Vitals, image weight. Use when the user asks about bundle size, performance regression, Lighthouse, LCP/CLS/INP, or wants a perf budget in CI.
---

# code-perf-budget

Budgets are only real if CI blocks on them. Design the budget, then wire the gate.

## Baseline

Measure current state before proposing a budget:

- Bundle: run the project's build; sum output by route/chunk. Frameworks vary — Next has `.next/analyze/`, Vite has `rollup-plugin-visualizer`, Webpack has `webpack-bundle-analyzer`.
- Images: `find <public dir> -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.webp' -o -name '*.avif' \)` → total bytes, largest 10.
- Fonts: total kb per weight/style.
- Lighthouse: one run against the built app (local or preview URL).

## Propose budgets

Set at "current + 10%" to catch regressions, not "aspirational" numbers that always fail.

Sample shape:
```
INITIAL JS (route /)          ≤ 180 KB gz    (today: 165 KB)
INITIAL CSS                    ≤ 30 KB gz     (today: 22 KB)
LARGEST IMAGE                  ≤ 200 KB       (today: 320 KB — over budget)
FONT PER WEIGHT/STYLE          ≤ 40 KB        (today: max 38 KB)
LIGHTHOUSE PERFORMANCE         ≥ 90           (today: 87 — under)
LCP                            ≤ 2.5s         (p75, field data preferred)
CLS                            ≤ 0.1
INP                            ≤ 200ms
```

## Wire the gate

- **Bundle**: `size-limit` (framework-agnostic) or `@next/bundle-analyzer` + custom check.
- **Lighthouse**: `lighthouse-ci` in a GH Actions workflow.
- **Images**: pre-commit or CI script running `sharp`/`squoosh` size check.
- Fail the build on regression. Post a PR comment with the delta.

Emit the config files to add; show diffs; require user approval before committing.

## Quick-wins list

Before setting the budget, propose one round of easy wins:

- Convert PNG > 50 KB to WebP/AVIF where DPR allows.
- Preconnect + preload for the LCP element.
- Font-display swap, subset if possible.
- Dynamic-import large route-only libs.
- Drop moment.js / lodash-full → date-fns / lodash-es tree-shaken.
- Remove unused polyfills for modern browsers.

## Hard rules

- Never propose a budget the current build already exceeds without also proposing the fix.
- Never enable a CI gate without a "dry-run" mode first (comment on PR, don't fail).
- Never delete an image or asset "to save bytes" without checking every reference.
