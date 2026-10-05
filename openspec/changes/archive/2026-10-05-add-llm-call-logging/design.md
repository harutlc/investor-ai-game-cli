## Context

See proposal.md for the motivation. The requirements are in `specs/llm-call-logging`, plus the modified `game-engine` and `cli-interface` requirements.

How LLM calls are made today:
- **Brain:** `InvestorBrain.judge()` builds the questions, then `SystemOneBackend.ask()` posts to `/v1/systemone` through `httpx.Client._post()`. It retries once on 429/529 within a 10-second deadline. The stub backend makes no HTTP calls.
- **Voice:** `GuardedVoice.render()` calls `backend.compose()` once, and a second time with a correction note when the number guard fails. If the backend raises, it falls back to templates. `OllamaVoiceBackend` posts `/api/chat` with httpx. `ClaudeVoiceBackend` calls `client.beta.messages.create(**params)` (or the non-beta `create`) on `anthropic` 1.11, which uses httpx2 internally. The SDK's `with_raw_response` returns an `APIResponse` exposing `http_request`, `status_code`, `headers`, `text` and `parse()`. Its exceptions carry `.request` (timeouts, connection errors) or `.response` (status errors).
- **Lifecycle:** `Session.new_game()` creates a `Game` via `Game.start()`, which renders the opening through the voice. `Game.play()` runs brain → policy → voice. A single `InvestorBrain` and a single `GuardedVoice` are shared by every game in a session.
- **Constraints:** turns must stay atomic. The voice must never raise. The CLI only sees `PlayerView`s. Default runs must still write nothing to disk.

## Goals / Non-Goals

**Goals:**
- Exact request and response bodies for every HTTP exchange with jev, laya, claude and ollama, in one file per exchange, with turn and purpose in the file name.
- No changes to the `BrainBackend`/`VoiceBackend` protocols or the turn pipeline's behaviour.
- Logging failures are invisible to game logic.

**Non-Goals:**
- Logging stubs or template fallbacks.
- Log rotation, retention, compression or a log viewer.
- Reloading or replaying games from logs.
- Logging the Brain insights or game state snapshots. `game.json` is metadata only.
- Python `logging` integration. This is a separate, structured artifact store; `--debug` stays as it is.

## Decisions

### D1. A small `llmlog.py` module with three pieces
- `LogRoot(path, secrets)`: owns the configured directory. `start_game(game_id, persona, pitch, backends) -> GameLog | None` creates the game folder: `YYYY-MM-DDTHH-MM-SS_g<id>_<persona>`, with a `-2`, `-3`, … suffix on collision, using `mkdir(exist_ok=False)` in a loop so the check-and-create is race-free. It then writes `game.json`.
- `GameLog`: the folder path, a per-service sequence counter, a `failed` flag and a one-shot `warning`. `record(exchange)` builds the file name, serialises and writes. It never raises.
- `Exchange` (a dataclass): service, model, method, url, request headers and body, response status/headers/body or `None`, error, `started_at` and `duration_ms`.

*Alternative:* the stdlib `logging` module with a file handler per game. It was rejected because a handler gives one stream per logger, not one file per exchange, and its formatting gets in the way of pretty-printed JSON documents.

### D2. Scope via `contextvars`, recording at the call site
The engine wraps each brain and voice call in `llmlog.scope(game_log, turn, purpose)`. This sets a `ContextVar` holding the active `GameLog`, the turn, the purpose and a per-service call counter for the scope. Backends call `llmlog.record(service, model, request=..., response=..., error=..., started_at=..., duration_ms=...)`. This is a no-op when no scope is active (logging off), or when the scope's `GameLog` is `None` or has failed.
- Purpose: the brain uses `move.kind` (`offer`/`message`); the voice uses `VoiceRequest.template_key` (`open`, `counter`, `hold`, …).
- `_retry` tagging: the scope counts calls per service. The second call to the same service in the same scope gets `_retry`, and a third would get `_retry2`. This covers both the brain's 429/529 retry and the voice's corrective retry without either backend knowing about turns.
- Stubs never call `record`, so they are excluded naturally.

*Alternatives:* (a) pass a recorder parameter through `judge()`/`ask()`/`render()`/`compose()`. This was rejected because it changes four protocols and every fake in the tests, just to carry metadata. (b) Wrap the HTTP transport. This was rejected because httpx and httpx2 are two different libraries, and the transport cannot see the turn or purpose.

### D3. Capturing exact bodies per backend
- **SystemOne (jev/laya)** in `_post()`: on success, record `response.request.method/url/headers/content` and `response.status_code/headers/content`. On an `httpx.TimeoutException`/`HTTPError`, record `exc.request` with `response=None` and `error={"type": "timeout"|"connection"}`. Non-200 responses are recorded as normal exchanges with `error={"type": "http_status"}`. Each of the two attempts on 429/529 produces its own file.
- **Ollama** in `compose()`: the same pattern via httpx.
- **Claude** in `compose()`: switch to `client.beta.messages.with_raw_response.create(**params)` (or the non-beta equivalent), then call `raw.parse()` for the message. Record `raw.http_request` and `raw.status_code/headers/text`. `APIStatusError` → `exc.response` (with `.request`), with error `http_status`. `APITimeoutError`/`APIConnectionError` → `exc.request`, with error `timeout`/`connection`. A `refusal` stop reason is recorded as a normal 200 exchange with `error={"type": "refused"}`. The existing mapping to `VoiceError` is unchanged.
- **Bodies:** bytes are decoded as UTF-8 and parsed as JSON when possible, falling back to text. This stores exactly what went over the wire, not a reconstruction.

### D4. File format and writing
- **Name:** `f"{seq:03d}_turn{turn:02d}_{purpose}{retry}.json"` in `<game>/<service>/`. The sub-folder is created lazily on the first record.
- **Content:** `json.dumps(doc, indent=2, ensure_ascii=False)`, with the fields defined in the spec. `started_at` comes from `datetime.now().astimezone().isoformat(timespec="milliseconds")`.
- **Writes are atomic:** write to `<name>.tmp`, then `os.replace`, so a crash never leaves half a JSON file.
- **Redaction:** headers in `{authorization, proxy-authorization, x-api-key, api-key, cookie, set-cookie}` (case-insensitive) become `[REDACTED]`. As a second layer, `LogRoot` receives the configured secret values (`TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`) and replaces any occurrence in the serialised text before writing.

### D5. Where the game folder is created and how the CLI learns about it
`Session` gets an optional `LogRoot` and the backend description. `new_game()` calls `start_game()` before `Game.start()`, so the opening voice call is logged under `turn00_open`, and passes the `GameLog` into `Game`. `Game.start`/`play` wrap `voice.render`/`brain.judge` in `llmlog.scope(...)`.

`PlayerView` gains two optional, non-secret fields: `log_folder: str | None`, and `log_warning: str | None` (set once when the `GameLog` first fails). The CLI prints the folder at negotiation start and in the debrief, and prints the warning the first time it appears. This keeps the CLI talking only to `PlayerView`, as the existing type-boundary test requires.

### D6. Configuration
`Settings` gains `log_dir: Path | None`, built from `--log-dir` or `INVESTOR_GAME_LOG_DIR`. `Settings.build` raises `ConfigError("The log directory must be a folder: …")` when the path exists and is not a directory. The directory itself is created lazily, on the first game. `cli/app.py` builds `LogRoot(settings.log_dir, secrets=[...])` only when `log_dir` is set, and the banner shows `logs: <dir>`.

### D7. Fault isolation and timing
`GameLog.record` catches `OSError` and `ValueError`/`TypeError` (serialisation). On the first failure it sets `failed=True` and stores `"LLM logging stopped for this game: could not write to <folder>."`. Later calls return immediately. `LogRoot.start_game` catches `OSError`, returns a `GameLog` already in the failed state with the warning, and the game proceeds. In `SystemOneBackend.ask`, the time spent recording the first attempt is added back to the deadline before a retry, so writing logs never eats into the 10-second budget. Voice calls are not deadline-chained, so they need no adjustment.

### D8. Tests
- `llmlog` unit tests: folder naming and collision suffix, sequence numbering, `_retry` tagging, redaction (header and value), JSON vs. text bodies, non-ASCII output, atomic write (no `.tmp` left behind), and the failure path (read-only directory → one warning, no exception).
- Adapter tests: respx-mocked Jev, Laya and Ollama inside a scope assert the files' request/response bodies equal what was sent and returned, including timeout and 429-retry files. Claude uses a fake client whose `with_raw_response.create` returns an object with `http_request`/`status_code`/`headers`/`text`/`parse()`. The existing Claude fakes are updated to that shape.
- Scenario tests: a full offline game with `--log-dir` produces only `game.json`. A game with mocked Ollama produces `voice-ollama/001_turn00_open.json` and one file per later turn. Without `--log-dir`, the existing smoke test still asserts that nothing is written.
- CLI: `--log-dir` pointing to a file exits non-zero; the banner, negotiation and debrief show the folder.

## Risks / Trade-offs

- [Logs hold the player's full text and the pitch] → Logging is opt-in and local-only. The README documents it, and `logs/` is added to `.gitignore`.
- [`contextvars` state can leak if a scope is not exited] → `scope()` is a context manager using `ContextVar.set`/`reset` in `finally`. The engine is single-threaded, and Rich's spinner thread never makes LLM calls.
- [The Claude switch to `with_raw_response` changes the call shape] → It is the documented SDK path and is covered by the updated fakes. A live smoke run with a real key remains a manual step (as before).
- [Disk usage grows with long sessions] → A game has at most about 15 brain and 30 voice exchanges of a few KB each, so the risk is small. Rotation is out of scope.
- [Redaction by header name can miss a new credential header] → Mitigated by the second value-based scrub of known key values.
