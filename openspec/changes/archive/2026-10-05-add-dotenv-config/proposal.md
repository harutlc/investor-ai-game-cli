## Why

The game is configured entirely through environment variables: API keys (`TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`), service URLs, model names, backend choices and the log directory. Exporting them in every shell, or typing them on every command line, is tedious and error-prone. A local `.env` file lets the player keep these settings in one place next to the project and simply run `investor-game`.

## What Changes

- On startup, `investor-game` (and `python -m investor_game`) reads a `.env` file from the current working directory, if one exists, and makes its variables available exactly as if they had been exported.
- **Precedence:** command-line flags win over the real environment, which wins over `.env`. A variable already set in the shell is never overwritten by `.env`.
- A missing `.env` is not an error. Lines that cannot be parsed are skipped, and the player sees one warning naming their line numbers, without the line contents (which may hold secrets). The game still starts.
- When a `.env` was loaded, the startup banner says so (for example, "settings: .env"). It never prints values.
- A committed `.env.example` lists every supported variable with comments and safe placeholders. `.env` is added to `.gitignore` so real keys are never committed.
- The README explains the setup: `cp .env.example .env`, fill in keys, run.

## Capabilities

### New Capabilities
<!-- None: .env support is part of how the CLI is configured. -->

### Modified Capabilities
- `cli-interface`: adds an "Environment file" requirement covering how `.env` is loaded, its precedence, error handling and the banner notice. The existing "Configuration" requirement is not edited, because the in-flight `add-llm-call-logging` change modifies it. The new behaviour is a separate requirement, so the two changes don't conflict.

## Impact

- **Code:** `src/investor_game/cli/app.py` (load `.env` in `main()` before Typer parses options, since Typer reads `INVESTOR_GAME_*` variables during parsing), plus a small helper module for loading and reporting. `config.py` is unchanged: it keeps reading `os.environ`.
- **Files:** a new `.env.example`, `.gitignore` gains `.env`, and the README gets a setup section.
- **Dependency:** `python-dotenv` (a small, widely used parser that handles quoting, `export` prefixes, comments and multi-line values).
- **Tests:** unit tests for loading, precedence and malformed lines. Tests that call `Settings.build(env=…)` or Typer's `CliRunner` directly are unaffected, because `.env` loading happens only in `main()`.
