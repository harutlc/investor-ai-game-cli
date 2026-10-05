## Why

Today the only visibility into the AI services is the Brain insights view. It shows interpreted answers, but not what was actually sent to Jev, Laya, Ollama or Claude, or what they returned. To debug prompts, tune the decision questions, investigate a wrong number caught by the guard, or show a tutor exactly what each model saw, we need the raw request and response bodies of every call, organised so that one game can be inspected on its own.

## What Changes

- New **opt-in** LLM call logging, enabled with `--log-dir PATH` or `INVESTOR_GAME_LOG_DIR`. When it is off, nothing is written to disk, as today.
- **One folder per game**, for example `<log-dir>/2026-10-05T11-42-07_g1_rex/`. Each game, including every "Play again", gets its own folder. The folder holds a small `game.json` with the investor, pitch, backends, models and start time.
- **One sub-folder per LLM** inside the game folder: `brain-jev/`, `brain-laya/`, `voice-claude/` or `voice-ollama/`.
- **One JSON file per request/response exchange**, numbered in call order and named by turn and purpose, for example `001_turn01_offer.json`, `002_turn01_counter.json` or `003_turn01_counter_retry.json`. Each file holds the request (method, URL, redacted headers, full body), the response (status, headers, full body) or the error, the timing, and the game turn.
- Only the real LLM backends (jev, laya, claude, ollama) are logged. The built-in stubs and template fallbacks are not.
- Credentials (`Authorization`, `x-api-key` and similar headers) are always redacted. Secret persona limits are never sent to any LLM, so they never appear in logs.
- A failure to write logs never breaks or delays a turn. The game warns once and continues without logging.
- When logging is on, the CLI shows the game's log folder at the start of the negotiation and in the debrief.
- **MODIFIED behaviour:** the "nothing is written to disk" rule now applies only while logging is off.

## Capabilities

### New Capabilities
- `llm-call-logging`: per-game folders, per-LLM sub-folders, one file per request/response exchange with full bodies, redaction, which backends are logged, file naming and ordering, and fault isolation.

### Modified Capabilities
- `game-engine`: the "In-memory games only" requirement now allows writing LLM call logs when logging is explicitly enabled. Games themselves stay in memory.
- `cli-interface`: the "Configuration" requirement gains `--log-dir` / `INVESTOR_GAME_LOG_DIR`, and the negotiation and debrief screens show the game's log folder when logging is on.

## Impact

- **Code:** a new `src/investor_game/llmlog.py` (log directory and game folders, the per-call recorder, redaction and file writing). Call-site recording in `brain/systemone.py`, `voice/ollama.py` and `voice/claude.py`; Claude switches to `with_raw_response` to capture the exact HTTP bodies. Game-folder creation and turn/purpose scoping in `engine.py`/`session.py`. A flag in `config.py`/`cli/app.py`, and the folder shown in `cli/screens.py`/`render.py`.
- **Tests:** new unit and adapter tests for the log files. The existing "no files written" smoke test stays valid for runs without `--log-dir`.
- **Dependencies:** none new.
- **Privacy:** the logs contain everything the models saw, including player messages, pitch text and full prompts. They stay local and are written only when the player opts in. The README will note this.
