# Ollama Code Browser

Ollama Code Browser is a local, file-browser-first web application for reading and editing project code with Ollama assistance. Its three-pane layout keeps the project tree and source code visible while you request summaries, detailed explanations, reviews, improvement ideas, or answers to free-form questions.

## Start the application

```bash
cd /path/to/CodeBrowser
./start.sh /path/to/your/project
```

Open <http://127.0.0.1:8092> in a browser. To use a different port:

```bash
PORT=9000 ./start.sh /path/to/your/project
```

The main application uses only the Python 3 standard library, so no package installation is required.

After startup, select **Open Folder** in the header to switch to another directory. Enter an absolute path to a local directory. After the switch, the application continues to prevent access outside the newly selected root.

## Features

- Lazily loaded project file tree
- Runtime root switching through **Open Folder**
- Pinned projects with actions for opening, structure summaries, improvement reviews, Loop, path copying, and unpinning
- Project-structure summaries from the context menu or mobile overflow menu
- Resizable Ollama Assistant panel with the selected width saved locally
- File summaries, detailed explanations, and reviews directly from the file context menu
- Folder-level structure summaries
- Whole-project improvement reviews using up to three models
- `Loop ×3` for as many as three rounds of multi-model analysis, consolidation, safe edits, and tests
- Mobile navigation between Files, Code, and AI panels
- English and Japanese interfaces and Ollama response-language selection
- Parent-directory navigation from the file browser
- Full-screen Ollama Assistant with `Esc` to restore the normal layout
- Up to eight analysis tabs with concurrent execution
- IndexedDB persistence for analysis tabs, generated content, the selected tab, and the last open file
- Grouped multi-model improvement runs with an integrated result showing agreements, disagreements, priorities, and an implementation plan
- Protection against duplicate multi-model runs
- Exclusion of the premium `kimi-k3` model from Ollama Cloud lists and automatic validation
- Clickable file and function references in Ollama responses, with matching source lines highlighted
- Source display with line numbers, language, line count, and file size
- Absolute-path display with a tooltip and one-click copy
- Global `READ ONLY` lock enabled by default; the server rejects saves and Git operations while it is active
- UTF-8 editing, external-change conflict detection, and atomic saves with `⌘S` or `Ctrl+S`
- Git branch and file-status display, plus an explicit commit action limited to the current file
- File-name filtering with `⌘K` or `Ctrl+K`
- Analysis of an entire file or a source selection
- Streaming Ollama responses and model selection
- Direct Markdown export with metadata
- Print-ready PDF export with Japanese-language support
- Automatic exclusion of `.git`, `node_modules`, virtual environments, build outputs, and other generated directories
- Path validation that prevents access outside the root selected at startup or through **Open Folder**

## Project structure summaries

Right-click a folder in the file browser, or use the mobile overflow menu, and select **Summarize this folder structure**. Code Browser generates the following information in the assistant panel:

- Project overview
- Technology stack
- Responsibilities of the main directories
- Entry points and important files
- A recommended reading order

Structure summaries are never triggered automatically at startup or when navigating between directories.

Code Browser sends Ollama a file tree limited to four levels and 1,200 entries, plus selected metadata files such as `README`, `package.json`, `pyproject.toml`, and `go.mod`. It does not send the entire source tree or the contents of `.env`. Results are cached for the current browser session to avoid duplicate model requests and can be exported as Markdown or PDF.

## Automated improvement Loop

`Loop ×3` in the assistant panel targets the current project. You can also limit the target through a file or directory context menu.

Each round performs the following steps:

1. Up to three models review the target independently.
2. The primary model consolidates the findings and produces strict JSON change candidates.
3. The server validates each target path, original file SHA-256, and file size.
4. Only validated UTF-8 source files are saved, using atomic replacement.
5. The application detects and runs either `python -m pytest` or `python -m unittest discover -s tests` when supported by the project structure.
6. Successful rounds are committed to a dedicated `ollama-loop/YYYYMMDD-HHMMSS` branch.
7. The Loop stops when no changes remain, three rounds complete, the user requests a stop, an error occurs, or `READ ONLY` is enabled.

Automated Loop edits are currently limited to Python (`.py`) files. A file Loop rejects non-Python targets. A project Loop may use broader structure information for context, but analysis, editing, and syntax validation remain limited to Python files.

When a Loop starts in a project that is not managed by Git, Code Browser creates a local repository and an initial commit at the project root. It excludes `.env`, private keys, databases, `data/`, logs, dependencies, and build outputs through `.git/info/exclude`. It does not configure a remote or push commits.

For an existing Git repository, the Loop starts only when the working tree is clean. It never stashes or overwrites pre-existing changes. A Loop cannot start while `READ ONLY` is enabled and stops before the next write if the lock is re-enabled. Model-generated shell commands are never executed.

If a model returns a path containing nonexistent directories, Code Browser corrects it only when exactly one authorized file has the same name. Ambiguous paths are rejected. Full-file responses containing patch markers or invalid Python syntax are rejected before saving. If detected tests fail or time out, all changes from that round are restored and no commit is created.

## Ollama connection order

### Direct Ollama Cloud connection (recommended)

Set an Ollama API key in the environment to connect directly to `https://ollama.com/api` without routing through a local Ollama server. The API key is never sent to the browser.

```bash
export OLLAMA_API_KEY="your_ollama_api_key"
./start.sh /path/to/your/project
```

To avoid storing the key in shell history:

```bash
read -s OLLAMA_API_KEY
export OLLAMA_API_KEY
./start.sh /path/to/your/project
```

You can also store the value in `.env` in the application directory. Code Browser loads this file at startup without overriding variables that are already present in the shell environment.

```dotenv
OLLAMA_API_KEY=your_api_key
```

`.env` is excluded by `.gitignore`.

### Without an API key

Code Browser tries these endpoints in order:

1. Endpoints specified by `OLLAMA_HOSTS`, when configured
2. `http://localhost:11434`

When it falls back to Ollama on the local Mac, Code Browser displays and uses only `:cloud` models to match the current workspace policy. It prefers a code-oriented 7B Coder model as the default.

To configure endpoints explicitly, set a comma-separated `OLLAMA_HOSTS` value in `.env` or the environment. API requests reject hosts outside this configured list. The model list is cached for 30 seconds and invalidated immediately when endpoint settings change.

```dotenv
OLLAMA_HOSTS=http://ollama-server.local:11434,http://localhost:11434
```

## Limitations and security boundaries

- Git commits are never created automatically outside the explicit Loop workflow. For a manual commit, disable `READ ONLY` and select **Git** for the target file.
- The maximum displayed file size is 1.5 MB.
- Binary files are not displayed.
- Code sent to Ollama is limited to 120,000 characters per request.
- The application is intended for trusted local environments. Do not expose it directly to the public internet.

HTTP responses include security headers such as Content Security Policy. Every POST API requires `X-Requested-With: CodeBrowser`; normal requests from the application include it automatically.

## Markdown and PDF export

The **Markdown** and **PDF** buttons become available after an analysis completes.

- **Markdown** downloads the target file, model, endpoint, creation time, and result as a `.md` file.
- **PDF** opens an A4 print layout. On macOS, select **PDF → Save as PDF** in the print dialog. The layout uses browser-provided Japanese fonts, so no additional package is required.

## ChatGPT MCP integration

The browser running Code Browser synchronizes pinned projects, the current project and file, and generated analysis tabs to a local `.code-browser-mcp-state.json` file. It does not store API keys or source-code contents in that state file.

Start the MCP server. On the first run, the script installs the official Python MCP SDK into a dedicated virtual environment.

```bash
cd /path/to/CodeBrowser
./start-mcp.sh
```

The local Streamable HTTP endpoint is `http://127.0.0.1:8766/mcp`. It exposes the following read-only tools:

- `list_pinned_projects`: list pinned projects
- `get_current_context`: return the current project, file, and `READ ONLY` state
- `list_analysis_results`: list metadata and previews for summaries, explanations, reviews, and improvement results
- `get_analysis_result`: return the complete text for a specified analysis ID
- `get_loop_status`: return the latest Loop target, branch, progress, and round summaries
- `get_loop_round`: return per-model analysis, changes, tests, and commit data for a specified round

When connecting from ChatGPT, do not expose the local port directly. Use ChatGPT Developer mode and Secure MCP Tunnel. In the ChatGPT Plugins connection flow, select Tunnel and configure it to reach this MCP endpoint. If you deploy the endpoint on public HTTPS infrastructure, add authentication.

Verify the protocol with:

```bash
.venv-mcp/bin/python scripts/check_mcp.py http://127.0.0.1:8766/mcp
```

## License

[MIT License](LICENSE)

This project is not affiliated with or endorsed by Ollama, Inc. Ollama is a trademark of Ollama, Inc.
