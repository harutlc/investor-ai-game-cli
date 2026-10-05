## ADDED Requirements

### Requirement: Environment file
When `investor-game` starts, it SHALL read a file named `.env` in the current working directory, if one exists, before any configuration is read. Each `NAME=value` entry SHALL become available exactly like an exported environment variable, for every setting the program reads from the environment: backend choice, keys, URLs, models, timeouts, offline mode and the log directory. Precedence SHALL be: command-line flags first, then variables already set in the real environment, then `.env`. A variable already present in the environment SHALL NOT be overwritten by `.env`. The file SHALL support comments (`#`), blank lines, an optional `export ` prefix, and single- or double-quoted values.

A missing `.env` SHALL NOT be an error, and SHALL produce no message. Lines that cannot be parsed SHALL be skipped, and the player SHALL see one warning listing their line numbers, never their contents. The program SHALL then continue. When a `.env` file was loaded, the startup banner SHALL say so (for example, "settings: .env") without showing any value. The repository SHALL ignore `.env` in version control and SHALL provide a committed `.env.example` that documents every supported variable with placeholder values.

#### Scenario: Keys from .env
- **WHEN** `.env` contains `ANTHROPIC_API_KEY=sk-ant-123` and `INVESTOR_GAME_VOICE=claude`, nothing else sets them, and the user runs `investor-game`
- **THEN** the game starts with the claude voice using that key, and no "required" error is shown

#### Scenario: Real environment wins
- **WHEN** `.env` contains `INVESTOR_GAME_BRAIN=jev` and the shell has `INVESTOR_GAME_BRAIN=stub` exported
- **THEN** the brain is `stub`

#### Scenario: Flag wins
- **WHEN** `.env` contains `INVESTOR_GAME_VOICE=ollama` and the user runs `investor-game --voice stub`
- **THEN** the voice is `stub`

#### Scenario: No .env file
- **WHEN** there is no `.env` in the current directory
- **THEN** the program starts normally, without any message about `.env`

#### Scenario: Malformed line
- **WHEN** line 3 of `.env` is `this is not valid` and the other lines are valid
- **THEN** the valid entries are applied, one warning mentions line 3 without showing its text, and the game starts

#### Scenario: Banner notice without values
- **WHEN** a `.env` with `ANTHROPIC_API_KEY=sk-ant-123` is loaded
- **THEN** the banner includes "settings: .env" and the output never contains `sk-ant-123`

#### Scenario: Secrets stay out of git
- **WHEN** the repository's ignore rules are checked
- **THEN** `.env` is ignored and `.env.example` is tracked
