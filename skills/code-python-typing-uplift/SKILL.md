---
name: code-python-typing-uplift
description: Add or improve type hints in a Python codebase incrementally — module by module, without breaking runtime. Use when the user asks to add types, improve mypy/pyright coverage, or migrate to strict typing.
---

# code-python-typing-uplift

Move from untyped to strictly-typed without a big-bang rewrite.

## Preflight

- Read `pyproject.toml` for existing `[tool.mypy]` / `[tool.pyright]` / `[tool.ruff]` config.
- Detect Python floor from `python_requires` / `python` classifier / `python-version`.
- Detect runtime deps that lack stubs (`types-<name>` needed).
- Baseline: run type-checker on current state, record error count.

## Order of operations

1. **Enable checker at "off" strictness** across the whole project.
2. Rank modules by (fan-in × complexity × current bug density).
3. Uplift one module at a time — public API signatures first, internals second.
4. Only after a module is clean, opt it in to strict via `[[tool.mypy.overrides]]` or `# pyright: strict`.

## Style rules

- Modern syntax when the floor allows: `list[str]` over `List[str]` (3.9+), `X | None` over `Optional[X]` (3.10+).
- `from __future__ import annotations` at top of file so annotations don't cost runtime.
- Prefer `Protocol` over `ABC` for structural typing at boundaries.
- `TypedDict` for dict shapes crossing module boundaries.
- `Literal` for enum-like string params before reaching for `Enum`.
- Avoid `Any` — if forced, alias it: `JsonScalar = str | int | float | bool | None; Json = JsonScalar | list["Json"] | dict[str, "Json"]`.

## Third-party gaps

- If a dep has no stubs, first check `types-<name>` on PyPI.
- If none, write a `.pyi` in `stubs/` and add `[[tool.mypy.overrides]] module = "..."` scoped to that lib.
- Never blanket-ignore an entire module with `# type: ignore`.

## Runtime safety

- Every uplifted module must import + run its tests before committing.
- If a runtime `isinstance` check contradicts a hint, the hint is wrong — fix the hint, don't cast it away.
- `cast()` is a last resort; `assert isinstance(...)` documents intent better.

## Report

Per-module: added / touched / delta on checker error count / current strictness level. End with the next-best module to uplift.
