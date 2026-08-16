# Metered Ollama Wrapper Architecture

Status: separate private Stage 0/1 prototype implemented; not approved for production
Date: 2026-08-16

## Decision

Code Browser can place a vendor-operated middleware between installed clients and Ollama Cloud. The middleware can keep the vendor's Ollama API key secret, proxy streaming responses, record per-user usage, enforce entitlements, and export aggregated usage to a billing provider.

Do not implement a tokenizer for billing. Treat Ollama's final `prompt_eval_count` and `eval_count` fields as the authoritative per-request token measurements. The custom implementation is the usage ledger, reservation and settlement logic, pricing, quota enforcement, and reconciliation—not tokenization.

Production launch is blocked until Ollama confirms in writing that the intended multi-user commercial proxy/resale model is permitted. The public Terms do not explicitly grant resale rights and prohibit automated access without permission and use to develop competing products.

The recommended product licensing split is documented in [Licensing Strategy](licensing-strategy.md): keep the public local client under MIT and operate the metered inference, identity, billing, and abuse-control backend from a separate private repository under commercial Terms.

Implementation note: the proprietary `code-browser-commercial-wrapper` project now implements the non-streaming internal prototype, including hashed API tokens, operation/model allowlists, monthly and prepaid credits, atomic reservation and settlement, actor-scoped idempotency, Ollama final-count validation, `metering_unknown`, append-only usage events, a billing outbox, and authenticated usage/model APIs. Its inference kill switch remains off by default. The private project's P0 TODO keeps written Ollama authorization and the remaining commercial launch controls as blockers.

## Proposed topology

```text
Code Browser client
        |
        | HTTPS + authenticated product operation + idempotency key
        v
API gateway / WAF
        |
        v
Auth + entitlement service ---- Free-tier and paid balance
        |
        v
Inference wrapper ------------ Usage reservation + append-only ledger
        |                                  |
        | fixed egress destination         v
        v                              Outbox worker ---- Stripe meter events
Ollama Cloud
```

The client submits a product operation such as `file_summary`, `project_summary`, or `review`; it does not receive a generic Ollama-compatible proxy. The wrapper owns model selection policy, system prompts, output ceilings, and the upstream host. This reduces key theft, SSRF, and use of the service as an unrelated low-cost inference endpoint.

## Freemium entitlement model

Use three distinct tiers:

1. **Anonymous trial** — a deliberately small promotional allowance. Limit by a server-issued anonymous grant, IP/network risk signal, device-local identifier, and bot challenge. These signals can be reset or evaded, so anonymous usage must be treated as an acquisition cost rather than a secure identity.
2. **Registered free account** — a monthly token or cost-unit allowance after verified sign-up. Enforce user, device, IP, concurrency, model, and global limits.
3. **Paid account** — start with prepaid credits or a monthly included allowance plus prepaid overage. Postpaid, uncapped usage should wait until fraud controls and reconciliation are proven.

When the anonymous allowance is exhausted, require registration. When the registered free allowance is exhausted, require a paid entitlement or wait for the published reset date. The server—not the client—calculates and returns remaining allowance.

Avoid advertising a single undifferentiated “token” when models have different upstream economics. Display model-specific input/output usage or normalized product credits, while preserving raw input and output token counts internally.

## Authoritative request lifecycle

1. Authenticate the account or validate a short-lived anonymous grant. Derive `actor_id` on the server.
2. Accept a random idempotency key scoped to the actor. Create a server request ID. A retry with the same key returns or reconnects to the existing logical request and never starts another upstream generation.
3. Validate a server-side operation ID, model allowlist, payload schema, source size, maximum context, maximum output, and concurrent-request limits.
4. Atomically reserve the worst-case cost from the actor's allowance using the selected immutable price version. Reject before contacting Ollama when the reservation cannot be made.
5. Insert an `accepted` usage event, then contact one hard-coded Ollama endpoint using a key from a managed secret store. Never accept an upstream URL or authorization header from the client.
6. Parse each Ollama NDJSON frame and forward safe response fields. Do not log prompts, source code, responses, or upstream authorization headers.
7. On the final `done` frame, validate non-negative integer `prompt_eval_count` and `eval_count`. Append a `measured` event and atomically settle the reservation against the immutable model price version.
8. Publish a billing-outbox record in the same database transaction. A worker sends aggregated Stripe meter events with stable identifiers and marks them delivered. Stripe is not called synchronously in the response path.
9. Keep enough metadata for audit and reconciliation: request ID, actor, operation, model, counts, price version, status, prompt byte length and hash, timestamps, and upstream completion reason. Do not retain prompt or response content by default.

### Client disconnects and missing final counts

A client disconnect does not prove that Ollama stopped generating. For the MVP, use a strict output ceiling and continue draining the already-started upstream response to its final frame so usage can be measured and settled. Do not start a duplicate when the client retries.

Later, test whether cancelling an Ollama Cloud stream reliably returns final usage. If cancellation produces authoritative counts, cancellation may replace draining. If the final usage frame is unavailable, record `metering_unknown`; do not invent billable token counts. Preserve the reservation until reconciliation or release it under a documented customer-favorable policy, while tracking the amount as vendor loss. Never silently delete the event.

## Minimal ledger

Use integer token counts and integer money micro-units or `Decimal`; never floating point.

```text
usage_requests
  request_id UUID primary key
  actor_id
  idempotency_key
  operation
  model
  price_version_id
  status: accepted | streaming | measured | failed | metering_unknown
  prompt_bytes
  prompt_sha256
  prompt_tokens nullable
  output_tokens nullable
  reserved_microcredits
  settled_microcredits nullable
  upstream_done_reason nullable
  created_at / completed_at
  unique(actor_id, idempotency_key)

usage_events (append-only)
  event_id UUID primary key
  request_id
  sequence
  event_type
  event_payload
  created_at
  unique(request_id, sequence)

billing_outbox
  event_id UUID primary key
  actor_id
  meter_name
  quantity
  status
  attempts
  next_attempt_at
  provider_event_id nullable
```

Corrections are compensating events, never edits to historical measurements. Each usage row references an immutable price version containing separate input and output rates or normalized credit weights.

## Security controls

- Use authorization-code login with PKCE. Prefer secure, HTTP-only, same-site cookies for the web/PWA; use OS secure storage for a future native client. Access tokens should be short-lived and revocable.
- Do not treat device fingerprinting as authentication. A random device identifier is an abuse signal only.
- Apply limits per anonymous grant, user, organization, device signal, IP/network, model, operation, and globally. Enforce concurrent-stream and daily spend ceilings before upstream calls.
- Place the Ollama API key in a secret manager, restrict egress to the fixed Ollama host, redact headers, rotate the key, and provide an emergency global kill switch.
- Accept only JSON with strict content type and byte limits. Reject client-controlled upstream URLs, arbitrary headers, tools, model options, system prompts, and unbounded chat history.
- Keep the wrapper private from direct browser discovery where possible; require a valid product session and CSRF protection. CORS is not authentication.
- Use TLS everywhere, WAF/bot controls at registration and anonymous grant creation, credential-stuffing protection, verified email, and payment fraud controls.
- Never log source code. Store only byte counts and a salted or keyed digest when correlation is necessary. Scrub exception trackers and traces.
- Clearly disclose that selected source content is sent through the vendor middleware to Ollama Cloud. Define retention, deletion, subprocessors, breach handling, and regional data-transfer terms.
- Monitor provider 401/402/429 errors, token/cost velocity, duplicate keys, metering-unknown rate, account-wide spend, and ledger-to-provider drift.

## Billing and reconciliation

Stripe meter events should be emitted from an outbox and use stable identifiers so retries cannot double-report usage. Batch or pre-aggregate events when appropriate. The product ledger remains the source for customer-visible usage; Stripe is an invoicing projection, not the primary ledger.

Reconcile at three levels:

1. accepted reservations versus measured/failed/unknown requests;
2. measured ledger totals versus billing events delivered to Stripe;
3. ledger totals and internal cost estimates versus any account-level usage or credit data Ollama makes available.

The third comparison is a launch dependency if Ollama offers a usable export. If no provider usage export exists, keep a conservative vendor-loss reserve and manually reconcile account credits while requesting an enterprise feed.

### Measuring estimation error

Code Browser now includes a local metering-audit prototype. Every completed interactive streamed analysis preserves Ollama's final input/output counters and compares them with a deliberately simple, tokenizer-independent estimate (`ceil(UTF-8 bytes / 4)`). The estimate is useful for sizing reservations and quantifying model/language drift; it is never a billable count. The production wrapper must meter Loop and all other non-interactive operations through the same ledger as well.

The UI shows measured input/output counts and signed estimation error after each response. The local endpoint `GET /api/metering/audit?limit=200` returns recent privacy-preserving records and aggregate error by provider and model. Records contain provider identity, byte counts, token counts, operation, timestamps, and request IDs, but never prompt or response text. The append-only prototype file is `.code-browser-metering-audit.jsonl` and is excluded from Git. Provider-plugin counts remain diagnostic and are never a source of billable managed usage.

Track at least these validation indicators separately for each model and operation:

- missing final-count rate;
- aggregate signed error, which reveals systematic over- or under-reservation;
- mean absolute field error, which reveals request-level volatility;
- p50/p95 error and language/content cohorts in the production ledger;
- ledger-to-billing and ledger-to-provider aggregate drift.

Do not declare one universal acceptable error without measured traffic. Establish a baseline per model, then alert on a material change from that baseline and on any missing authoritative count. The production wrapper must replace the local JSONL prototype with its transactional append-only database ledger.

## Go / No-Go gates

1. Written Ollama approval or a commercial agreement covering multi-tenant proxying/resale.
2. A measured experiment confirming final token fields for every allowed cloud model, including streaming, errors, timeouts, and disconnects.
3. A tested reservation/settlement ledger with unique idempotency and crash recovery.
4. Anonymous and account quotas that cap worst-case vendor spend, plus a global kill switch.
5. Verified unit economics per model, including free acquisition cost, payment fees, taxes, refunds, and fraud.
6. Privacy terms and data-processing disclosures appropriate for customer source code.
7. Stripe test-mode reconciliation and signed webhook handling before live billing.
8. Customer Terms, Privacy Policy, Pricing/Credit Policy, and the public/private licensing boundary reviewed for commercial launch.

## Staged delivery

- **Stage 0:** internal wrapper, one model, non-streaming, upstream counters recorded, no customer billing.
- **Stage 1:** streaming, reservation/settlement, disconnect tests, immutable price versions, usage dashboard.
- **Stage 2:** registered free accounts, monthly reset, concurrency/rate/spend limits, anonymous trial with a very small allowance.
- **Stage 3:** prepaid paid accounts and Stripe meter-event outbox in test mode.
- **Stage 4:** production billing after Ollama commercial approval, reconciliation, privacy review, and abuse testing.

## Recommended initial product decision

Proceed with a proof of concept, but do not launch “shared Ollama account as a paid service” yet. First obtain Ollama's written approval. Build the metering ledger independently of Ollama so another inference provider or a dedicated commercial Ollama agreement can replace the upstream without changing customer accounts and billing history.
