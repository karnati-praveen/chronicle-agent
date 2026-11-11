# Chronicle — Search & Remember Agent

A compact research chat agent with **one external tool: `web_search`**. It uses an OpenAI-compatible chat model, Brave Search or Tavily, and SQLite/FTS5 to remember what you asked and when.

## Why Chronicle

- **One tool only:** the model can search the public web; no shell, browser automation, or external actions are exposed.
- **Timestamped memory:** messages and search events are stored with UTC timestamps.
- **Useful recall:** FTS5 retrieves relevant earlier messages from the active session so follow-ups can refer to prior questions.
- **Grounded answers:** results are normalized, numbered, and shown as source cards. Source cards are persisted with the assistant message, so they survive a page reload. The model is instructed to distinguish evidence from inference.
- **Your data, on demand:** export a full session as JSON or delete it entirely (messages, FTS index, search events) from the sidebar or the API.
- **Fast bounded loop:** at most five search results per call and two tool-call rounds per answer.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and provide:

- `LLM_API_KEY` — API key for an OpenAI-compatible chat-completions provider.
- `LLM_BASE_URL` and `LLM_MODEL` — provider endpoint and model name.
- `BRAVE_API_KEY` with `SEARCH_PROVIDER=brave`, **or** `TAVILY_API_KEY` with `SEARCH_PROVIDER=tavily`.

Start the server:

```bash
uvicorn main:app --reload
```

Open http://127.0.0.1:8000.

## Tests

```bash
pytest -q
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `LLM_API_KEY` | Chat model credential | Required |
| `LLM_BASE_URL` | OpenAI-compatible API base URL | OpenAI default |
| `LLM_MODEL` | Chat model identifier | `gpt-4.1-mini` |
| `SEARCH_PROVIDER` | `brave` or `tavily` | `brave` |
| `BRAVE_API_KEY` | Brave Search credential | Required for Brave |
| `TAVILY_API_KEY` | Tavily Search credential | Required for Tavily |
| `CHRONICLE_DB` | SQLite file path | `./data/chronicle.db` |
| `MAX_HISTORY_MESSAGES` | Recent messages passed to the model | `12` |
| `RATE_LIMIT_PER_MINUTE` | Max `/api/chat` requests per minute per client IP (`0` disables) | `20` |

Responses include restrictive security headers (a strict Content-Security-Policy, `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy`). The per-process rate limiter is intentionally simple; multi-instance deployments should enforce limits at the reverse proxy instead.

## API

- `POST /api/chat` — `{ "message": "...", "session_id": "optional" }`. Rate limited per client IP (returns `429` with a `Retry-After` header when exceeded).
- `GET /api/history?session_id=...` — chronological conversation (including persisted source cards) plus search history. Read-only: unknown sessions return empty lists.
- `GET /api/memory/search?q=...&session_id=...` — timestamped lexical recall matches. Read-only.
- `GET /api/export?session_id=...` — download the full session (messages, sources, tool events) as JSON. `404` for unknown sessions.
- `DELETE /api/session?session_id=...` — delete the session and all its messages, FTS index rows, and search events. Returns `{"deleted": true|false}`.
- `GET /health` — health check; verifies the SQLite database is reachable (`503` when degraded).

## Design

See [`DESIGN.md`](DESIGN.md) for the architecture, single-tool contract, memory model, latency choices, correctness strategy, trade-offs, and evaluation checklist.

## Privacy and limitations

Privacy: conversation history and search metadata are stored in the local SQLite database. The sidebar **Clear conversation** button and `DELETE /api/session` erase a session and all of its derived records; **Export** (`GET /api/export`) produces a portable JSON copy. Do not use this demo with sensitive conversations on a shared machine. Session IDs are not authentication. A production deployment still needs authentication, authorization, retention/deletion policies, encryption, and distributed rate limits. Search snippets may omit context from the full source pages.

## License

MIT. See [`LICENSE`](LICENSE).
