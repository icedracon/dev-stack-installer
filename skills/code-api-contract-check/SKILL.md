---
name: code-api-contract-check
description: Detect drift between the API server implementation and its published contract (OpenAPI, tRPC, GraphQL SDL, protobuf). Use when the user asks to audit API contract, verify OpenAPI, or check client/server type parity.
---

# code-api-contract-check

Contract and code drift silently. Find the gap.

## Detect the contract source

- `openapi.{yaml,yml,json}`, `swagger.*`, `**/api-spec.*`
- tRPC routers (`appRouter`) + client packages
- GraphQL: `**/*.graphql`, `**/schema.gql`, codegen configs
- `**/*.proto` + generated bindings

If multiple exist, ask which is authoritative.

## Server-side extraction

Enumerate actual routes / procedures / resolvers:

- Express/Fastify/Hono: grep `app.<method>('/path'`, `router.<method>`.
- FastAPI/Flask: decorators (`@app.<method>`, `@router.<method>`).
- Django REST / Rails: `urls.py`, `routes.rb`, viewset actions.
- tRPC: walk the router tree, collect procedure names + input/output schemas.
- GraphQL: resolver map vs. SDL.
- gRPC: service methods vs. `.proto`.

For each, capture: path, method, path params, query params, request schema, response schema (per status).

## Compare

Emit a drift table:

```
OP                                CONTRACT     SERVER       STATUS
GET /users/{id}                   ✓            ✓            match
POST /users                       ✓            ✓            body: server accepts extra `role` field
DELETE /orders/{id}               ✓            —            missing on server
POST /users/{id}/promote          —            ✓            undocumented endpoint
```

Also: **shape drift** — same op, different field names / types / required-ness.

## Response-status matrix

For each endpoint list documented vs. actually-returnable statuses. `404` for a wrong-shape id? `422` for validation? `429` for rate limit? Undocumented statuses break generated clients.

## Client parity (if a client codegen is used)

- Regenerate the client to a scratch dir; diff against committed client. Any diff = the contract changed since last codegen.
- Flag hand-edited codegen output — that is a maintenance trap.

## Report

- Grouped by severity: missing endpoint / breaking shape change / undocumented endpoint / cosmetic (description, examples).
- Each finding cites both the contract line and the server line.

## Hard rules

- Never regenerate the contract or client without asking.
- Never mark a diff "cosmetic" if a field name or type differs — that breaks clients.
