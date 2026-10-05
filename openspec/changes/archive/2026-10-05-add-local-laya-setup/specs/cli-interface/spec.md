## MODIFIED Requirements

### Requirement: Configuration
The command SHALL accept `--brain {jev,laya,stub}`, `--voice {claude,ollama,stub}`, `--offline` (short for stub brain and stub voice), `--brain-timeout`, `--voice-timeout`, `--log-dir PATH` and `--version`. Each option SHALL have an environment-variable equivalent (`INVESTOR_GAME_BRAIN`, `INVESTOR_GAME_VOICE`, `INVESTOR_GAME_LOG_DIR`, etc.). Backend settings SHALL be read from the environment: `TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL`, `TYPESAFE_MODEL`, `LAYA_BASE_URL`, `LAYA_MODEL`, `LAYA_API_KEY`, `ANTHROPIC_API_KEY`, `INVESTOR_GAME_CLAUDE_MODEL`, `OLLAMA_HOST` and `INVESTOR_GAME_OLLAMA_MODEL`. `LAYA_MODEL` and `LAYA_API_KEY` SHALL be optional. Missing required settings for the chosen backend SHALL be reported before the game starts, with the name of the missing variable. If `--log-dir` points to an existing path that is not a directory, the program SHALL report it before the game starts and exit with a non-zero code.

#### Scenario: Missing Anthropic key
- **WHEN** the user runs `investor-game --voice claude` with no `ANTHROPIC_API_KEY`
- **THEN** the program prints that `ANTHROPIC_API_KEY` is required for the claude voice, and exits with a non-zero code

#### Scenario: Log directory from the environment
- **WHEN** the user runs `investor-game` with `INVESTOR_GAME_LOG_DIR=./logs`
- **THEN** LLM call logging is enabled with `./logs` as the log directory

#### Scenario: Log directory is a file
- **WHEN** the user runs `investor-game --log-dir notes.txt` and `notes.txt` is an existing file
- **THEN** the program prints that the log directory must be a folder, and exits with a non-zero code before the Setup step

#### Scenario: Laya without optional settings
- **WHEN** the user runs `investor-game --brain laya` with neither `LAYA_MODEL` nor `LAYA_API_KEY` set
- **THEN** no setting is reported as missing, and the game starts
