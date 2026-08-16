# Ollama-compatible provider plugin

This is the MIT-licensed reference implementation of Code Browser Provider Plugin SDK v1. It connects to an Ollama or Ollama-compatible `/api/tags` and `/api/chat` service using credentials supplied by the user.

Configure Code Browser through `.env`:

```dotenv
CODE_BROWSER_PROVIDER_PLUGIN=ollama-compatible
OLLAMA_PLUGIN_BASE_URL=http://localhost:11434
OLLAMA_PLUGIN_API_KEY=
```

For a remote service, use an HTTPS origin and set `OLLAMA_PLUGIN_API_KEY` when required. The plugin rejects base URLs containing embedded credentials, paths, queries, or fragments.

The host passes only the two environment variables declared in `code-browser-plugin.json`. The API key is used inside the plugin subprocess and is not returned to the browser.

This connector is a BYOK integration. The user is responsible for the provider account, charges, terms, privacy, and model availability. Plugin-reported token counts are diagnostics and are not accepted as GK Works managed-service billing records.
