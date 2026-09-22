---
name: ops-docker-slim
description: Audit a Dockerfile for image size, layer efficiency, security (non-root user, pinned base), reproducibility (pinned versions, no `latest`), and build cache friendliness. Use when the user asks to shrink an image, review a Dockerfile, or fix a slow build.
---

# ops-docker-slim

A Dockerfile is a build script AND a runtime spec. Audit both.

## Read the Dockerfile

Also read any sibling `.dockerignore`, `docker-compose*.yml`, `Makefile` targets that build the image.

## Base image

- **Pinned digest** (`sha256:...`) or at least a specific tag (`python:3.12.5-slim-bookworm`), never `latest` / bare major.
- Prefer `-slim` / `-alpine` / `distroless` for runtime.
- If Alpine: check the app's C deps (musl vs. glibc issues — psycopg, cryptography wheels, etc.).

## Multi-stage

- Build tools (`gcc`, `make`, dev headers, `node_modules` with dev deps) belong in a builder stage, never the final image.
- Final stage should `COPY --from=builder` only artifacts, not the whole `/app`.
- Rebuild-friendly stage order: put slow / rarely-changing steps first (`apt install`, `pip install`, `npm ci`), source last.

## Layer efficiency

- Every `RUN apt-get install` must end with `rm -rf /var/lib/apt/lists/*` in the same `RUN`.
- Never `COPY . .` before installing deps — kills cache on every source edit.
- Multiple `RUN` for related setup → one `RUN` (fewer layers).
- Use `--mount=type=cache` (buildkit) for package managers.

## Reproducibility

- Pin package versions (`apt-get install -y foo=1.2.3-1`, `pip install foo==1.2.3`, `npm ci`).
- Deterministic timestamps (`SOURCE_DATE_EPOCH`) if bit-for-bit needed.
- No `curl | sh` from unpinned URLs.

## Security

- `USER <non-root>` before `CMD`. Create the user in the image; don't rely on host uid.
- No secrets in `ENV` or `ARG` that end up in image layers — use buildkit secrets.
- `HEALTHCHECK` present for services.
- Don't `ADD` remote URLs; `RUN curl` + verify checksum is auditable.

## Startup / signals

- `ENTRYPOINT ["exec", "form"]` (not shell form) so signals reach PID 1.
- Or use `tini` / `dumb-init` if the app spawns children.

## .dockerignore

Must exclude at minimum: `.git`, `node_modules` (before install), `.env*`, `target/`, `dist/`, `.venv/`, IDE folders. Missing dockerignore = huge context and possibly leaked secrets.

## Report

```
IMAGE SIZE
- current (est.): 1.4 GB
- projected after fixes: 180 MB

BLOCKING
- runs as root
- .env copied into image (Dockerfile:24)

HIGH
- base tag `python:3.12` (unpinned minor)
- COPY . . before pip install (destroys cache)

LOW
- no HEALTHCHECK
```

## Hard rules

- Never propose Alpine without checking the app builds on musl.
- Never remove a `RUN` line without knowing what it installs.
- Never suggest distroless if the app needs a shell / debug tools in prod.
