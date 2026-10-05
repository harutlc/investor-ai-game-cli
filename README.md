# Investor Negotiation Game (CLI)

Negotiate a startup investment against an AI investor, in your terminal. You pitch your
startup, pick one of six investors, and bargain over **how much money** they put in and
**what share of the company** (equity) they get. See [`PRD.md`](PRD.md) for the full game design.

The investor is built from three parts:

- **Brain**: a decision AI that answers short, typed questions (would I accept? how good is
  this offer? is this an insult or a manipulation attempt?). It never writes chat text.
- **Game master**: deterministic rules in [`policy.py`](src/investor_game/policy.py). They
  keep the investor's secret limits and choose exactly one action per turn (accept, counter,
  reject, clarify, dismiss or walk away). They also compute every number.
- **Voice**: a text AI that writes the reply in the investor's style and suggests your next
  moves. A number guard checks every € amount and % against the decision. A wrong number
  gets one retry, then a plain sentence is used instead.

There is no server, database or web UI. Games live **in memory only**, so quitting the
program discards them.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run investor-game --offline      # built-in stub brain + voice, no network needed
```

Also available as `uv run python -m investor_game`.

## How to play

1. **Setup**: choose an investor (1-6), then press Enter to accept the GreenCharge example
   pitch or type your own. Money accepts `500000`, `500k`, `2M` or `€2,000,000`.
2. **Negotiation**: each turn, type an option number, or:
   - `o` to make a precise offer (amount, then equity %). You'll see the valuation it implies.
   - `m` to write a free message, including offers in words ("€500k for 15%, we have
     another fund interested").
   - `i` to open **Brain insights**: every question the brain was asked, with its answer,
     confidence, backend and latency. Answers below 55% confidence are marked *uncertain*.
   - `h` for help, `q` to walk away.
3. **Debrief**: see the outcome, the final terms or where it stopped, and the turns used.
   You can re-read the conversation, view insights, play again, or browse "Your games" for
   this run.

The game ends on a deal, when either side walks away, or after 15 turns. Mood hints show
interest (Low/Medium/High) and patience in words only. The investor's real numbers stay
hidden.

## Choosing AI backends

| Flag | Env var | Values | Needs |
|---|---|---|---|
| `--brain` | `INVESTOR_GAME_BRAIN` | `jev`, `laya`, `stub` | jev: `TYPESAFE_API_KEY` (optional `TYPESAFE_BASE_URL`, `TYPESAFE_MODEL`). laya: a local server at `LAYA_BASE_URL` (default `http://localhost:8000`, optional `LAYA_MODEL`) |
| `--voice` | `INVESTOR_GAME_VOICE` | `claude`, `ollama`, `stub` | claude: `ANTHROPIC_API_KEY` (optional `INVESTOR_GAME_CLAUDE_MODEL`, default `claude-opus-5-5`). ollama: a local Ollama at `OLLAMA_HOST` (default `http://localhost:11434`, optional `INVESTOR_GAME_OLLAMA_MODEL`, default `llama3.1`) |
| `--offline` | `INVESTOR_GAME_OFFLINE` | | Forces `stub` for both |
| `--brain-timeout` | `INVESTOR_GAME_BRAIN_TIMEOUT` | seconds, default 10 | |
| `--voice-timeout` | `INVESTOR_GAME_VOICE_TIMEOUT` | seconds, default 60 | |
| `--log-dir` | `INVESTOR_GAME_LOG_DIR` | folder | Log every LLM request/response (see below) |
| `--debug` | `INVESTOR_GAME_DEBUG` | | Detailed errors on stderr |

Without flags, the game uses Jev when `TYPESAFE_API_KEY` is set and Claude when
`ANTHROPIC_API_KEY` is set. Otherwise it uses the stubs.

```bash
TYPESAFE_API_KEY=... ANTHROPIC_API_KEY=... uv run investor-game          # Jev + Claude
uv run investor-game --brain laya --voice ollama                         # all local
INVESTOR_GAME_OLLAMA_MODEL=qwen2.5:3b uv run investor-game --voice ollama
```

If the brain fails or times out, your move is refused and the game stays exactly as it was,
so you can try again. If the voice fails, the turn still completes with a template reply
and system-built options. Jev and Laya share one HTTP adapter (`POST /v1/systemone`).

### Settings in a `.env` file

Rather than exporting variables in every shell, keep them in a `.env` file in the
project folder:

```bash
cp .env.example .env      # every line starts commented out
$EDITOR .env              # uncomment and fill in, e.g. ANTHROPIC_API_KEY=... INVESTOR_GAME_VOICE=claude
uv run investor-game      # the banner shows "settings: .env" when it was loaded
```

- `.env` is read from the folder you run the game in, so run from the project folder.
- Precedence: command-line flags win over variables exported in your shell, and those win
  over `.env`. An exported variable is never overwritten.
- Values may be quoted. `${OTHER_VAR}` is expanded in unquoted or double-quoted values;
  use single quotes for a literal `$`.
- A line that can't be parsed is skipped with a warning naming its line number. Its
  contents are never printed.
- `.env` is git-ignored, so keys stay out of the repository. `.env.example` documents every
  supported variable.

## LLM call logs

Add `--log-dir PATH` (or set `INVESTOR_GAME_LOG_DIR`) to record every request sent to the
real AI services, along with each response. Logging is off by default, and without it
nothing is written to disk.

```bash
uv run investor-game --brain jev --voice claude --log-dir logs
```

Each game, including every "Play again", gets its own folder. Inside it there is one
sub-folder per model service, and one JSON file per HTTP call:

```
logs/
  2026-10-05T11-42-07_g1_rex/
    game.json                      # investor, pitch, backends + models, start time
    brain-jev/
      001_turn01_offer.json        # NNN = call order, turnTT, purpose = move kind
      002_turn02_message.json
      003_turn02_message_retry.json  # retry after HTTP 429/529
    voice-claude/
      001_turn00_open.json         # the opening offer
      002_turn01_counter.json      # purpose = the decided action
      003_turn01_counter_retry.json  # corrective retry after a wrong number
  2026-10-05T11-48-30_g2_grace/
    ...
```

Each exchange file contains:

```json
{
  "service": "voice-ollama", "model": "qwen2.5:3b", "game": 1, "turn": 1,
  "purpose": "counter", "sequence": 2,
  "started_at": "2026-10-05T11:42:31.204+04:00", "duration_ms": 1843,
  "request":  { "method": "POST", "url": "http://localhost:11434/api/chat",
                "headers": { "...": "..." }, "body": { "model": "...", "messages": ["..."] } },
  "response": { "status": 200, "headers": { "...": "..." }, "body": { "message": { "...": "..." } } },
  "error": null
}
```

- `request.body` is exactly the JSON that was sent. `response.body` is the JSON that came
  back, or the raw text if the body isn't JSON. On a timeout or connection error, `response`
  is `null` and `error.type` says what happened.
- Only real models are logged (jev, laya, claude, ollama). The built-in stubs and template
  fallbacks are not, so an `--offline` game folder contains only `game.json`.
- Credential headers (`authorization`, `x-api-key`, …) are written as `[REDACTED]`, and
  configured API keys are scrubbed from the whole file. Secret investor limits are never
  sent to any model, so they never appear in logs.
- **Privacy:** logs contain everything the models saw, including your messages, the pitch
  and the full prompts. They stay on your machine, and `logs/` is git-ignored.
- If a log can't be written (for example, the folder isn't writable), the game shows one
  warning and keeps playing without logging.

## Development

```bash
uv run pytest            # unit, adapter (respx), CLI and full-game scenario tests
uv run ruff check src tests
```

- `src/investor_game/`: `money.py`, `models.py`, `personas.py`, `policy.py`, `engine.py`,
  `session.py`, `config.py`; `brain/` (questions, extraction, stub, System One adapter);
  `voice/` (prompts, guard, stub, Claude, Ollama); `cli/` (Typer app, screens, Rich render).
- `tests/scenarios/` plays full offline games against every persona. It includes a
  secret-leak test that records every screen and checks that no budget, minimum equity or
  numeric mood ever appears.

### Manual playtest notes (5 October 2026)

- `--offline`: full games against Grace (deal at €500k for 16%, turn 2) and Rex (walk away),
  plus the Your games list and debrief menus.
- `--brain stub --voice ollama` with `qwen2.5:3b`: in-character replies. The number guard
  corrected the small model's wrong numbers on retry (shown as "corrected after retry" in
  Brain insights) and used the plain sentence for the opening.
- `--brain stub --voice ollama --log-dir …` with `qwen2.5:3b`: the game folder held
  `game.json` and `voice-ollama/001_turn00_open.json` … `006_turn03_player_walked.json`,
  including `_retry` files where the guard caught a reply missing the decided terms. The
  retry's request body shows the correction note sent to the model.
- Jev, Laya and Claude: not playtested (no keys or server on the test machine). They are
  covered by adapter tests with mocked HTTP responses and a faked Anthropic client.
