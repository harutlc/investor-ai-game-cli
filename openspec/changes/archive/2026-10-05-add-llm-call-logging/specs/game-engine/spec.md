## MODIFIED Requirements

### Requirement: In-memory games only
Games SHALL be kept only in process memory. The system SHALL keep a list of the games played during the current run, newest first, and all games SHALL be discarded when the program exits. The system SHALL NOT write game data to disk, with one exception: when LLM call logging is explicitly enabled (see llm-call-logging), it SHALL write only the LLM call logs and `game.json` files under the configured log directory. Games SHALL NOT be loaded back from those logs.

#### Scenario: No files written
- **WHEN** a full game is played without LLM call logging enabled and the program exits
- **THEN** no game data files have been created

#### Scenario: Only logs written when logging is enabled
- **WHEN** a full game is played with `--log-dir` set and the program exits
- **THEN** the only files created are inside the configured log directory
