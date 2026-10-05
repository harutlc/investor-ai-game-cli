## 1. Log store

- [x] 1.1 Create `src/investor_game/llmlog.py` with `Exchange`, `LogRoot` and `GameLog` (design D1). Game-folder naming is `YYYY-MM-DDTHH-MM-SS_g<id>_<persona>`, with a race-free `-2`, `-3` collision suffix, and `game.json` is written on start. Verify with unit tests for folder naming, collision suffix and `game.json` content (number, start time, persona, pitch, backends and models)
- [x] 1.2 Implement `GameLog.record`: lazy per-service sub-folder, 3-digit per-service sequence, file name `NNN_turnTT_<purpose>[_retry].json`, pretty UTF-8 JSON with `ensure_ascii=False`, and an atomic tmp+replace write. Verify with tests for names and order, `€` written as-is, and no `.tmp` files left behind
- [x] 1.3 Implement body decoding (bytes → JSON, else text, else `null`) and redaction: credential headers become `[REDACTED]` case-insensitively, and configured secret values are scrubbed from the serialised text. Verify that the tests' header and value secrets never appear in a written file
- [x] 1.4 Implement `llmlog.scope(game_log, turn, purpose)` (a ContextVar that is reset in `finally`) and `llmlog.record(...)`. Recording is a no-op without a scope or with a failed log, and `_retry`/`_retry2` tagging comes from per-service call counts within a scope. Verify with tests: nothing is written outside a scope, the second call in the same scope is tagged `_retry`, and the scope is reset after an exception
- [x] 1.5 Implement fault isolation (design D7). `OSError`/serialisation errors set `failed` plus a one-shot warning and never raise, and `start_game` failure returns a failed `GameLog`. Verify with a read-only directory test: no exception, exactly one warning, and later records are silent

## 2. Backend recording

- [x] 2.1 Record every `SystemOneBackend._post` attempt (success, non-200, timeout and connection error) with the exact request and response bodies, adding the recording time back to the deadline before a 429/529 retry. Verify with respx tests for Jev and Laya inside a scope: one file per attempt, `request.body` equals the sent JSON, `response.body` equals the returned JSON, a timeout file has `response: null` and `error.type: "timeout"`, a 429→200 sequence gives `…_offer.json` and `…_offer_retry.json`, and the bearer token never appears
- [x] 2.2 Record every `OllamaVoiceBackend.compose` call (success, non-200, connection error, and a non-JSON body stored as text). Verify with respx tests for each case, checking the files' request and response bodies
- [x] 2.3 Switch `ClaudeVoiceBackend.compose` to `with_raw_response.create` (beta and non-beta paths), parse the message from the raw response, and record `http_request`/status/headers/text. Map `APIStatusError`/`APITimeoutError`/`APIConnectionError` to recorded errors, and record a `refusal` as `error.type: "refused"`, keeping the existing `VoiceError` mapping. Update the Claude test fakes to the raw-response shape and verify the existing Claude tests still pass, plus new tests showing the file's request body is the sent JSON and that `x-api-key` and the key value never appear

## 3. Engine, session and view

- [x] 3.1 Thread the log through the game: `Session(..., log_root=None, backends=...)` creates a `GameLog` per `new_game` before `Game.start`, and `Game` wraps the opening voice call in `scope(turn=0, purpose="open")`, each brain call in `scope(turn, move.kind)` and each voice call in `scope(turn, template_key)`. Verify with an engine test using recording fakes: the opening and per-turn calls carry the expected turn, purpose and retry tags, and a game without a log root records nothing
- [x] 3.2 Add `log_folder` and `log_warning` to `PlayerView`, populated from the game's `GameLog`. Verify that a view with logging off has both as `None`, that the existing no-secret-fields test still passes, and that a failed log surfaces its warning on the view
- [x] 3.3 Confirm atomicity with logging on: a brain failure with logging enabled still leaves `GameState` unchanged (the timeout/connection exchange file is written, but the turn is not applied). Verify with an engine test

## 4. Configuration and CLI

- [x] 4.1 Add `log_dir` to `Settings` (`--log-dir` / `INVESTOR_GAME_LOG_DIR`), with a `ConfigError` when the path exists and is not a directory, and build a `LogRoot` with the configured secrets in `cli/app.py` only when it is set. Verify with config tests for the env var, the flag and the file-path error (non-zero exit before Setup)
- [x] 4.2 Show the log information in the CLI: the banner shows `logs: <dir>`, the negotiation start shows "LLM logs: <game folder>", the debrief repeats it, and a `log_warning` is printed once when it first appears. None of this is shown when logging is off. Verify with scripted-terminal tests for the on and off cases and the single warning
- [x] 4.3 Add `logs/` to `.gitignore` and document `--log-dir` in the README: the folder layout, the file format example, the redaction note, and the privacy note that logs contain player text and prompts. Verify the README example paths match a real offline run with `--log-dir`

## 5. End-to-end verification

- [x] 5.1 Add scenario tests: an offline game with `--log-dir` produces a game folder holding only `game.json`; a two-game run produces two folders (`_g1_…`, `_g2_…`); and a game with respx-mocked Ollama produces `voice-ollama/001_turn00_open.json` plus files for later turns. Verify they pass with `uv run pytest tests/scenarios`
- [x] 5.2 Keep the no-disk guarantee: the existing subprocess smoke test (no `--log-dir`) still asserts that nothing is written, and a new subprocess run with `--log-dir` writes only inside that directory. Verify both pass
- [x] 5.3 Run `uv run ruff check src tests` and the full `uv run pytest`, and verify both are clean. Then play one game manually with `--voice ollama --log-dir logs` against the local Ollama, inspect the files for full bodies and correct turn/purpose names, and note the result in the README playtest section
