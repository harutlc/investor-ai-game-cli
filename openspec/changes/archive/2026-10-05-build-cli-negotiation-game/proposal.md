## Why

The Investor Negotiation Game (see `PRD.md`) lets a player practise a startup investment negotiation against an AI investor. The investor has a separate "brain" that makes decisions, a "voice" that writes the replies, and game rules that own every number. The PRD describes a browser game with a web server and an API. We want the same game as a **self-contained Python command-line program**, with no API, backend or web server. It should be quick to run, easy to inspect and easy to test, while keeping the brain/voice/rules split that the course assignment requires.

## What Changes

- New Python 3.12+ package and console command `investor-game`. It runs the whole game in one terminal process using rich interactive prompts (Typer + Rich).
- **Setup step:** choose one of six investor personas, then enter a pitch (name, sector, description, pre-money valuation, ask). The GreenCharge example is pre-filled, and the implied equity is shown.
- **Negotiation step:** the investor makes an opening offer. Each turn the player either picks a generated option, makes a precise offer (amount + equity %, with the implied valuation shown before sending) or writes a free message. Every turn shows a deal panel, mood hints (words only) and a "thinking" spinner. A `Brain insights` view can be opened at any time.
- **Debrief step:** shows the outcome and reason, the final terms (investment, equity, pre-/post-money compared with the ask) or "Where it stopped", and the turns used. It also offers to replay the transcript or play again.
- **Investor brain:** a pluggable decision AI with three backends: **Jev** (TypeSafe hosted, `POST /v1/systemone`), **Laya** (local, using its Jev-compatible self-hosted server) and a deterministic **stub**. It asks typed Noul/Choice/Score questions and records answers, confidences, backend and latency.
- **Investor voice:** a pluggable text AI with three backends: **Claude** (Anthropic API), **Ollama** (local) and a **template stub**. It writes in-character replies and 3–5 suggested player options. A number guard checks every number in a reply against the game's decision. If a number is wrong, the voice gets one retry, and after that the game uses a plain fallback sentence.
- **Game rules / policy:** pure-Python rules hold each persona's secret limits. They turn brain judgments into one action (accept / counter / reject / clarify / dismiss / walk away), compute counter-offer numbers, update interest and patience, and enforce the 15-turn limit and the end conditions.
- **In-memory state only:** games live only for the lifetime of the process. A "Your games" list shows games played in the current run. Nothing is written to disk.
- Configuration through environment variables and command-line flags. These choose the brain and voice backends, keys, URLs, models and timeouts. `--offline` uses both stubs and needs no network.
- **Removed from the PRD scope:** HTTP API, web UI, cookies and anonymous player IDs, persistence across runs, per-player rate limiting, light/dark theme switching and container deployment.

## Capabilities

### New Capabilities
- `investor-personas`: the six investor personas: visible profile (name, emoji, description, traits), secret limits, behavioural parameters (concession rate, patience, sensitivity) and voice style.
- `game-engine`: the in-memory game lifecycle: creating a game from a pitch and persona, the opening offer, applying a turn atomically, valuation maths, mood-hint mapping, turn limit, end conditions and refusing moves on finished games.
- `negotiation-policy`: the deterministic rules that turn brain judgments and secret limits into exactly one investor action, compute counter-offer numbers, and update interest and patience.
- `investor-brain`: the decision AI interface and its Jev, Laya and stub backends. This covers the questions asked each turn, offer extraction from free text that never invents numbers, manipulation detection, confidence and "uncertain" marking, timeouts, and failure semantics.
- `investor-voice`: the text AI interface and its Claude, Ollama and stub backends. This covers in-character replies, generated player options (always including accept and walk away), the number guard, retry and fallback, and treating player text as untrusted.
- `cli-interface`: the terminal experience across Setup, Negotiation and Debrief. This covers input validation messages, the three reply modes, the deal panel, mood hints, the Brain insights view, the in-session games list, configuration flags and safe error messages.

### Modified Capabilities
<!-- None: this is a greenfield project with no existing specs. -->

## Impact

- **New code:** `src/investor_game/` (domain models, personas, engine, policy, brain adapters, voice adapters, CLI) and `tests/`.
- **New dependencies:** `typer`, `rich`, `httpx` (Jev/Laya/Ollama HTTP), `anthropic` (Claude) and `pydantic` (validated models). Dev dependencies: `pytest`, `pytest-asyncio` or sync equivalents, and `respx` for HTTP mocking.
- **External services, all optional:** TypeSafe API (`TYPESAFE_API_KEY`), a local Laya server, the Anthropic API (`ANTHROPIC_API_KEY`) and a local Ollama daemon. The game is fully playable offline with the stubs.
- **No servers, databases or files are created at runtime.** Quitting the program discards all games.
