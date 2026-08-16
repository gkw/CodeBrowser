# Code Browser Provider Plugin SDK v1

Status: public experimental protocol  
License: MIT, as part of the Code Browser repository

## Purpose

Provider plugins let a Code Browser user connect a third-party LLM with credentials they control. The public SDK contains the provider boundary and a reference Ollama-compatible plugin. It does not contain GK Works credentials, commercial prices, entitlement rules, Stripe integration, fraud controls, or the managed-service ledger.

The initial protocol is deliberately small and provider-neutral. Plugins list models and execute Code Browser's server-created analysis messages. The host never accepts plugin-defined file edits, shell commands, tools, or arbitrary application actions.

## Trust boundary

A provider plugin is executable code, not passive configuration. Installing one grants it the operating-system permissions of the Code Browser process. Out-of-process execution prevents accidental Python imports and limits environment-variable inheritance, but it is not an OS sandbox.

- Plugins are disabled unless `CODE_BROWSER_PROVIDER_PLUGIN` explicitly selects one.
- The host launches the selected Python entrypoint without a shell.
- The entrypoint must remain inside its plugin directory.
- Only environment variables named in the manifest are passed to the process.
- Plugin stderr is discarded so provider secrets cannot be reflected into the UI.
- Requests, responses, model names, token counts, time, and output sizes are validated.
- Source is sent only to the selected plugin when the user runs an analysis.

Install only plugins whose publisher and source you trust. Signature verification, permission prompts, package checksums, revocation, and OS-level sandboxing are future requirements for a public marketplace.

## Manifest

Each plugin occupies one directory beneath a configured plugin root and contains `code-browser-plugin.json`.

```json
{
  "id": "example-provider",
  "name": "Example provider",
  "version": "1.0.0",
  "description": "Connect to Example LLM with user-owned credentials.",
  "publisher": "Example, Inc.",
  "license": "MIT",
  "homepage": "https://example.com/code-browser-plugin",
  "type": "provider",
  "protocolVersion": 1,
  "entrypoint": "plugin.py",
  "environment": ["EXAMPLE_API_KEY", "EXAMPLE_BASE_URL"]
}
```

The machine-readable manifest schema is [`provider-plugin-manifest.schema.json`](provider-plugin-manifest.schema.json).

Bundled plugins live under `plugins/providers`. Additional roots can be supplied through the platform path separator in `CODE_BROWSER_PLUGIN_DIRS`.

## Protocol

Version 1 uses one JSON-RPC 2.0 request and one response over stdin/stdout for each process. The process exits after its response. Streaming and long-lived sessions are intentionally deferred until cancellation, reconnection, memory limits, and lifecycle behavior are specified.

Model discovery request:

```json
{"jsonrpc":"2.0","id":"1","method":"models.list","params":{}}
```

```json
{"jsonrpc":"2.0","id":"1","result":{"models":["provider-model"]}}
```

Inference request:

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "inference.run",
  "params": {
    "requestId": "application-request-id",
    "operation": "summary",
    "model": "provider-model",
    "messages": [
      {"role": "system", "content": "Code Browser instruction"},
      {"role": "user", "content": "Selected source context"}
    ],
    "maximumOutputTokens": 4096
  }
}
```

Token usage is optional because some providers do not return it:

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "content": "Analysis result",
    "usage": {"promptTokens": 120, "outputTokens": 80}
  }
}
```

Plugin-reported counts are shown as diagnostics. They are not trusted for GK Works billing. Only the private managed inference service may produce billable usage.

## Reference Ollama-compatible plugin

The bundled `ollama-compatible` plugin works with a user's own Ollama or compatible account:

```dotenv
CODE_BROWSER_PROVIDER_PLUGIN=ollama-compatible
OLLAMA_PLUGIN_BASE_URL=http://localhost:11434
OLLAMA_PLUGIN_API_KEY=
```

For a remote account, use HTTPS and provide the user's own key through `OLLAMA_PLUGIN_API_KEY`. The key is passed only to the selected plugin subprocess and is never sent to the browser.

Provider plugins currently cover interactive file analysis, project summaries, and multi-model improvement reports. The automated editing Loop remains on the built-in Ollama path until the plugin protocol defines provider capabilities, structured-output guarantees, cancellation, and billing semantics for automated edits.

## Compatibility policy

- Additive result fields may appear in protocol v1 and must be ignored by plugins.
- Removing fields, changing field meaning, or adding required behavior requires a new protocol version.
- A plugin must not print logs to stdout; stdout is reserved for the JSON-RPC response.
- Plugins should not retain source or model output unless their own clearly disclosed policy requires it.
- Provider trademarks and API terms remain the plugin publisher's responsibility.
