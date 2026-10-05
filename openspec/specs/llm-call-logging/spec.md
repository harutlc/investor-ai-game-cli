# llm-call-logging Specification

## Purpose

Records every request sent to the real AI services (the Jev or Laya decision models and the Ollama or Claude text models) together with their responses, as local JSON files organised by game and by model. This lets developers and tutors see exactly what each model received and returned.

## Requirements

### Requirement: Opt-in logging
LLM call logging SHALL be off by default. It SHALL be enabled only when a log directory is configured with `--log-dir PATH` or `INVESTOR_GAME_LOG_DIR`. When logging is off, the system SHALL NOT create any log files or folders.

#### Scenario: Default run writes nothing
- **WHEN** a full game is played without `--log-dir` or `INVESTOR_GAME_LOG_DIR`
- **THEN** no log files or folders are created

#### Scenario: Directory created on demand
- **WHEN** logging is enabled with a log directory that does not exist yet, and a game starts
- **THEN** the directory is created, including missing parent folders

### Requirement: One folder per game
When logging is enabled, each game SHALL get its own folder directly under the log directory, created when the game starts. This includes every "Play again" in the same run. The folder name SHALL be `<local start time YYYY-MM-DDTHH-MM-SS>_g<game number>_<persona id>`. If that name already exists, a numeric suffix (`-2`, `-3`, …) SHALL be added. The folder SHALL contain a `game.json` file with the game number, start time, persona id and name, the pitch, and the brain and voice backends with their model names.

#### Scenario: Two games in one run
- **WHEN** logging is enabled and the player finishes a game with Rex, then plays again with Grace
- **THEN** the log directory contains two game folders, one ending in `_g1_rex` and one ending in `_g2_grace`, each with its own `game.json`

#### Scenario: Name collision
- **WHEN** a game folder with the computed name already exists
- **THEN** the new game uses the same name with a `-2` suffix, and the existing folder is left untouched

### Requirement: One sub-folder per LLM
Inside a game folder, exchanges SHALL be grouped into one sub-folder per model service: `brain-jev`, `brain-laya`, `voice-claude` or `voice-ollama`. A sub-folder SHALL be created only when that service is first called during the game.

#### Scenario: Jev brain with Claude voice
- **WHEN** a game is played with `--brain jev --voice claude` and logging enabled
- **THEN** the game folder contains `brain-jev/` and `voice-claude/` sub-folders and no other LLM sub-folders

### Requirement: Only real LLMs are logged
Calls handled by the built-in stub brain, the stub voice or the voice's template fallback SHALL NOT produce log files, because no model is called.

#### Scenario: Stub brain with Ollama voice
- **WHEN** a game is played with `--brain stub --voice ollama` and logging enabled
- **THEN** the game folder contains `voice-ollama/` but no `brain-*` sub-folder

#### Scenario: Fully offline
- **WHEN** a game is played with `--offline` and logging enabled
- **THEN** the game folder contains only `game.json`

### Requirement: One file per request/response exchange
Every HTTP request sent to a logged service SHALL be written to its own JSON file in that service's sub-folder. This includes retries: the brain's single retry after a 429 or 529, and the voice's corrective retry after a number-guard failure. Files SHALL be named `NNN_turnTT_<purpose>.json`, where:
- `NNN` is a 3-digit sequence number that increases with call order within the sub-folder, starting at 001;
- `TT` is the 2-digit game turn the call belongs to (00 for the opening offer);
- `<purpose>` is the player move kind for the brain (`offer` or `message`) and the decided action for the voice (for example `open`, `counter`, `hold`, `reject`, `accept`);
- a `_retry` suffix marks a repeat of the previous call.

#### Scenario: Turn with a voice correction
- **WHEN** on turn 1 the Jev brain is called once, the Claude voice reply fails the number guard and Claude is called again
- **THEN** `brain-jev/` gains one file named `…_turn01_offer.json` (or `_message`), and `voice-claude/` gains `…_turn01_counter.json` followed by `…_turn01_counter_retry.json` with the next sequence number

#### Scenario: Opening offer
- **WHEN** a game starts with the Ollama voice and logging enabled
- **THEN** `voice-ollama/001_turn00_open.json` exists

### Requirement: Full request and response bodies
Each exchange file SHALL be UTF-8, pretty-printed JSON with these fields:
- `service`, `model`, `game`, `turn`, `purpose` and `sequence`;
- `started_at` (ISO 8601 local time with offset) and `duration_ms`;
- `request`: `method`, `url`, `headers` and `body`, where `body` is exactly the JSON document that was sent;
- `response`: `status`, `headers` and `body`, where `body` is the parsed JSON document that was received, or the raw text when it is not valid JSON; `response` SHALL be `null` when no response was received;
- `error`: `null`, or an object with a `type` (for example `timeout`, `connection`, `http_status` or `refused`) and a short `message`.

Non-ASCII characters such as `€` SHALL be written as-is, not escaped.

#### Scenario: Successful Jev call
- **WHEN** a Jev request succeeds
- **THEN** the file's `request.body` equals the JSON body sent to `/v1/systemone` (model, state, questions), and `response.body` equals the JSON returned (answers, usage), with `error` `null`

#### Scenario: Non-JSON reply from Ollama
- **WHEN** Ollama returns a body that is not valid JSON
- **THEN** the file stores that body as a text string under `response.body`

#### Scenario: Timeout
- **WHEN** a brain request times out
- **THEN** a file is still written with the full request, `response` `null`, and `error.type` `timeout`

### Requirement: Credentials are redacted
Request and response headers that carry credentials SHALL be written with the value `[REDACTED]`. This covers at least `authorization`, `proxy-authorization`, `x-api-key`, `api-key`, `cookie` and `set-cookie`, matched case-insensitively. API keys SHALL NOT appear anywhere in a log file.

#### Scenario: Jev bearer token
- **WHEN** a Jev call is logged while `TYPESAFE_API_KEY` is `ts-secret-123`
- **THEN** the file shows `"authorization": "[REDACTED]"` and does not contain `ts-secret-123` anywhere

#### Scenario: Anthropic key
- **WHEN** a Claude call is logged while `ANTHROPIC_API_KEY` is `sk-ant-xyz`
- **THEN** the file does not contain `sk-ant-xyz` anywhere

### Requirement: Logging never breaks the game
A failure to create a folder or write a log file SHALL NOT fail, retry or change a turn, and SHALL NOT change the game state. On the first such failure, the player SHALL see one plain warning that logging has stopped for this game, and later write failures in that game SHALL be silent. Writing a log file SHALL NOT count toward the brain or voice time limits.

#### Scenario: Unwritable log directory
- **WHEN** logging is enabled with a directory the program cannot write to, and a game is played
- **THEN** the game plays normally, and the player sees a single warning that LLM logging is unavailable
