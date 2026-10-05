## Context

See proposal.md for the motivation and `specs/cli-interface` for the requirement. How configuration is read today:
- `cli/app.py::main()` calls the Typer `app()`. Typer resolves options that have `envvar=` (`INVESTOR_GAME_BRAIN`, `…_VOICE`, `…_OFFLINE`, `…_BRAIN_TIMEOUT`, `…_VOICE_TIMEOUT`, `…_LOG_DIR`, `…_DEBUG`) from `os.environ` **while parsing**, before `play()` runs.
- `config.Settings.build(env=None)` then reads keys, URLs and models from `os.environ` (or from an injected mapping in tests).
- `python -m investor_game` goes through the same `main()`.
- No `.env` support exists, and `python-dotenv` is not a dependency.

Probed with python-dotenv 1.2.4: `dotenv.parser.parse_stream()` yields one binding per statement, with `.key`, `.value`, `.original.line` and `.error`. A malformed line gives `error=True` with its line number. `dotenv_values()` returns the parsed mapping and handles `export`, quotes and comments. The library also logs "python-dotenv could not parse statement starting at line N" through the `dotenv.main` logger.

## Goals / Non-Goals

**Goals:**
- `.env` values become visible to both Typer and `Settings` with zero changes to `config.py`.
- Real environment and flags keep priority. Secrets are never printed.
- Tests stay hermetic: a developer's own `.env` cannot change test results.

**Non-Goals:**
- An `--env-file PATH` option or searching parent directories. The working directory only, by convention; this can be added later.
- Multiple env files (`.env.local`, per-mode files) or writing `.env` from the program.
- Validating values beyond what `Settings` already does.

## Decisions

### D1. Load in `main()`, before Typer parses
`main()` calls `load_env_file(Path.cwd() / ".env", os.environ)`, then `app()`. Loading inside `play()` would be too late for options declared with `envvar=`.
*Alternative:* pass `default_map`/context settings to Typer. This was rejected because it would only cover Typer options, not the variables `Settings` reads directly.

### D2. A small `env_file.py` helper on top of python-dotenv
```python
@dataclass(frozen=True)
class EnvFileResult:
    path: Path
    loaded: bool            # file existed and was read
    applied: tuple[str, ...]  # names set from the file (not values)
    bad_lines: tuple[int, ...]

def load_env_file(path: Path, environ: MutableMapping[str, str]) -> EnvFileResult
```
It reads the text once. `parse_stream` collects `bad_lines`, and `dotenv_values(stream=StringIO(text))` gets the values, with dotenv's default `${VAR}` interpolation. For each `key, value` with `value is not None` and `key not in environ`, it sets `environ[key] = value`, so the real environment always wins. During the call, the `dotenv.main` logger is muted, so the user sees only our single warning. A missing file returns `loaded=False`, and an unreadable file (`OSError`/`UnicodeDecodeError`) returns `loaded=False` plus a warning. Neither raises.
*Alternative:* our own parser. This was rejected because quoting, escapes, `export` and multi-line values are easy to get subtly wrong, and python-dotenv is small and standard.

### D3. Reporting
- **Warning:** `main()` prints one line to stderr when `bad_lines` is non-empty: `Warning: .env line(s) 3, 7 could not be read and were skipped.` It never echoes line contents.
- **Banner:** `main()` stores the result in a module-level `_ENV_FILE`. `play()` appends ` · settings: .env` to `settings.describe()` when `_ENV_FILE.loaded` is true. Values are never shown. `CliRunner` tests that call `app` directly see `_ENV_FILE = None`, so nothing changes for them.

### D4. Repository files
- `.env.example`: every supported variable, grouped (backends, Jev/Laya, Claude/Ollama, timeouts, logging, debug), with a one-line comment each. **Every assignment is commented out**, so `cp .env.example .env` changes nothing until the user uncomments a line. Without this, placeholder keys would select real backends with bogus credentials.
- `.gitignore`: add `.env`. `.env.example` stays tracked.
- A test keeps `.env.example` honest: it collects every variable name the code reads (`envvar="…"` in `cli/app.py` and `get("…")` in `config.py`) and asserts each appears in `.env.example`.

### D5. Tests
- `load_env_file` unit tests with an injected dict: values applied; existing keys kept (real env wins); `export`/quotes/comments; bad line numbers reported; missing file; unreadable file; no values in the result.
- `main()` tests in a temp working directory: monkeypatch `sys.argv`, `cwd` and the environment, and assert the backend selected from `.env`, a flag overriding `.env`, the banner "settings: .env", the warning on stderr, and that secrets are absent from the output. A subprocess smoke test runs the installed console script with a `.env` in its working directory.
- Hermeticity: existing subprocess smoke tests run in an empty `tmp_path`, so no `.env` is present. Unit tests never call `main()` without a controlled `cwd`.

## Risks / Trade-offs

- [A developer's `.env` in the repo root affects manual runs] → This is intended. The banner's "settings: .env" makes it visible.
- [Running from another directory does not find `.env`] → Documented in the README ("run from the project folder"). An `--env-file` option is a possible follow-up.
- [`${VAR}` interpolation surprises a value containing `$`] → Documented; use single quotes to keep a literal `$` (python-dotenv does not interpolate single-quoted values).
- [Relying on `dotenv.parser.parse_stream`, which is a public module but not in the top-level API] → The dependency is pinned to `python-dotenv>=1.0,<2`. If it moves, the fallback is to detect bad lines by comparing `dotenv_values` keys against a line scan, and the unit tests will catch any breakage.
