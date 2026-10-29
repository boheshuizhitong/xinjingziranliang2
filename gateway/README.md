# PowerContext Rust Gateway

An optional Rust executor for PowerContext, defined by the gateway design in #2199 and the context-protection contract in #2264. The gateway owns the model traffic boundary; every decision stays in PowerContext Core ("no policy in the gateway").

> Status: working prototype, verified end-to-end against a real PowerContext Server (PR #2264 branch) with real upstream providers. Depends on the `/v1/context/check` contract and `include_reuse` from #2264.

## What it does

- **Two-phase gate executor**: `check(before_send)` → send admitted bytes → `check(before_release)` → release. Opaque bindings thread the two phases; unknown never becomes allow; deterministic non-delivery retries are bounded, indeterminate sends are never auto-retried.
- **Memory injection**: per user message, calls `prepare` (`include_reuse`), injects the returned prepared context verbatim into the current user message, and declares the exact UTF-8 byte range (`prepared_contexts`) for Core-side digest verification.
- **Sedimentation**: after a released turn, synchronously captures the transcript via `capture_content_source` (idempotent `source_id` derived from the release binding). Blocked or degraded turns are never captured.
- **Deployment forms**: combined (Rust owns the public TCP port, Core listens on a private Unix socket only; all non-`/gateway` routes are reverse-proxied to Core over UDS) or standalone (TCP, remote Core).
- **OpenAI-compatible ingress** at `/gateway/v1/chat/completions` and `/gateway/v1/responses` (same format in and out, no cross-format translation), with streaming ingestion (strict buffering before release).
- **Middleware chain**: composable `GatewayMiddleware` trait; ships with resource limits (body size + concurrency) and request-id propagation.

## Layout

| Crate | Responsibility |
| --- | --- |
| `pc-gateway-app` | thin binary: ingress, port-takeover proxy, middleware chain |
| `pc-gateway-core` | executor state machine, GateClient (check/prepare/capture/capabilities) over TCP or UDS |
| `pc-gateway-types` | contract DTOs aligned field-by-field with #2264 |
| `pc-gateway-protocol` | canonical request, chat/responses wire renderers, SSE framing |
| `pc-gateway-transport` | upstream transport, bounded retry, streaming buffer with caps |
| `pc-gateway-evidence` | body-free evidence (usage completeness, cache tokens, TTFT) |
| `pc-gateway-embedded` | placeholder for the in-process (FFI) executor path |

## Run

```bash
cargo build --release

# Combined deployment (Core on a Unix socket)
PC_GATEWAY_CORE_UDS=/path/to/pc.sock \
PC_GATEWAY_UPSTREAM_PROFILE=<approved profile name> \
PC_GATEWAY_DEFAULT_SCOPE=<scope id> \
PC_GATEWAY_UPSTREAM_URL_CHAT=https://provider/v1/chat/completions \
PC_GATEWAY_UPSTREAM_API_KEY_CHAT=... \
./target/release/pc-gateway

# Optional: PC_GATEWAY_INJECTION=on (prepare + inject), PC_GATEWAY_SEDIMENT=on (capture after release),
# PC_GATEWAY_DEGRADE=passthrough (no-memory passthrough when Core is unreachable; never applies
# to deployments with enforcing protection), PC_GATEWAY_MAX_CONCURRENT / PC_GATEWAY_MAX_BODY_BYTES.
```

Credentials live only in server-side environment variables; they are never accepted from request fields and never enter check payloads.

## Tests

`cargo test` — 27 tests covering the failure-semantics table (gate unavailable, withhold terminal, bounded retry, indeterminate no-resend, blocked turns never sediment), renderer fidelity (no timestamps/request ids injected), byte-range declaration, and UDS connection-pool correctness over a real Unix socket.
