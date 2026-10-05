## 1. Loader

- [x] 1.1 Add `python-dotenv>=1.0,<2` to `pyproject.toml` dependencies, and verify `uv sync` succeeds and `uv run python -c "import dotenv"` works
- [x] 1.2 Create `src/investor_game/env_file.py` with `EnvFileResult` and `load_env_file(path, environ)` (design D2): it parses once, applies only keys not already in `environ`, records bad line numbers, mutes the `dotenv.main` logger, and never raises (missing → `loaded=False`; unreadable → `loaded=False` plus a warning). Verify with unit tests for applied values, real-env-wins, `export`/quotes/comments, line 3 reported as bad while other lines still apply, missing file, an unreadable/non-UTF-8 file, and that the result holds no values

## 2. CLI wiring

- [x] 2.1 Call `load_env_file(Path.cwd() / ".env", os.environ)` in `cli/app.py::main()` before `app()`, store the result in `_ENV_FILE`, and print the single stderr warning for bad lines without their contents. Verify with `main()` tests in a temp working directory: a `.env` with `INVESTOR_GAME_VOICE=claude` and `ANTHROPIC_API_KEY` passes the missing-key check; an exported `INVESTOR_GAME_BRAIN=stub` beats `.env`'s `jev`; `--voice stub` beats `.env`'s `ollama`; and no `.env` means no message
- [x] 2.2 Append ` · settings: .env` to the banner when `.env` was loaded. Verify that the banner text appears, that the output (stdout and stderr) never contains the secret value from `.env`, and that existing `CliRunner` tests are unchanged
- [x] 2.3 Add a subprocess smoke test that runs the installed `investor-game` in a temp directory containing a `.env` with `INVESTOR_GAME_OFFLINE=true` and a malformed line. Verify exit code 0, "settings: .env" in stdout, and the line-number warning on stderr

## 3. Repository files and docs

- [x] 3.1 Add a committed `.env.example` listing every supported variable, with all assignments commented out and a one-line comment each (design D4), and add `.env` to `.gitignore`. Verify with a test that every variable read in `cli/app.py` (`envvar=`) and `config.py` (`get("…")`) appears in `.env.example`, and with `git check-ignore .env` succeeding while `.env.example` is not ignored
- [x] 3.2 Document the setup in the README: `cp .env.example .env`, uncomment and fill in, run from the project folder, the precedence (flags > real environment > `.env`), the quoting note for literal `$`, and that `.env` is git-ignored. Verify by following the steps with an offline `.env` and seeing "settings: .env" in the banner

## 4. Verification

- [x] 4.1 Run `uv run ruff check src tests` and the full `uv run pytest`, and verify both are clean, including all existing tests unchanged
