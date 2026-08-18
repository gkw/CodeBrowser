# Code Browser development guidance

## Preferred architecture

- Treat serverless as the preferred future direction, while preserving the file-browser-first local workflow.
- Keep a clear boundary between the local companion and the serverless control plane. The local companion handles filesystem access, Git, local Ollama, PDF access, and capabilities requiring user-machine authority.
- Prefer the serverless control plane for authentication, subscriptions, Code Browser Credits, token metering, provider routing, MCP access, and asynchronous Deep Read or Loop jobs.
- Prefer static/PWA edge delivery, stateless handlers, durable queues/workflows, and managed persistence for account, job, and metering state. Long model calls must be resumable, observable, cancellable, and safe to retry.
- Keep source code and private files local by default. Remote analysis must be explicit, bounded, documented in the UI, and limited to the minimum required context. Never expose Ollama or wrapper secrets in browser code.
- Preserve local/offline or BYOK operation where practical. Managed-service outages, quotas, cold starts, and network latency must not silently remove the local-first path.
- For architecture decisions, evaluate local versus serverless responsibility, data movement and consent, durable state, retries/idempotency, execution limits, CBC/cost, observability, provider lock-in, and fallback behavior. Record material decisions and alternatives in `docs/decisions/`.
