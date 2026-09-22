---
name: design-component-doc
description: Generate or update per-component documentation (props table, variants, usage examples, a11y notes) from React / Vue / Svelte / Angular source. Use when the user asks to document a component, generate a Storybook story, or produce a component README.
---

# design-component-doc

Read the component source and emit a doc a designer or downstream dev can actually use.

## Extract from source

- Props: name, type, default, required, JSDoc/TSDoc description.
- Variants: enum-typed prop values, plus `cva`/`tv`/`clsx`-based variant maps.
- Slots / children: what's expected (typed children? render prop?).
- Emitted events (Vue/Svelte) or callbacks (React).
- `forwardRef` / ref-forwarding pattern.
- `aria-*` and `role` present in the JSX/template.

## Output — one file per component

Default location: `<Component>.md` next to the source, unless the project has a `docs/` convention.

```md
# <Component>

<one-line intent>

## Props

| name | type | default | description |
|------|------|---------|-------------|

## Variants
- primary | secondary | ghost
- sm | md | lg

## Usage
```tsx
<Button variant="primary" size="md" onClick={…}>Save</Button>
```

## A11y
- role: button (native)
- keyboard: Enter / Space
- focus ring: visible via `focus-visible:ring-2`

## Related
- [[design-tokens]] for the color/space tokens used
- [[design-ui-audit]] for parity checks
```

## Storybook mode

If `.storybook/` exists OR `**/*.stories.*` present, also generate a story:
- One story per variant × size.
- Include `parameters.a11y` if `@storybook/addon-a11y` is installed.
- Use CSF3 syntax.

## Hard rules

- Never invent props that aren't in the source.
- Never mark a prop `required` unless the source does (`?` absence in TS, `required: true` in Vue).
- Never claim a11y a component does not implement.
