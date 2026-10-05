## Context

This is a greenfield repository: it holds `PRD.md` and an empty `openspec/`, and has no code yet. The PRD describes a web product. This change rebuilds the same game as a single Python process with a terminal UI (see proposal.md, Why). The user made these choices: the brain runs on **Jev + Laya + stub**; the voice runs on **Claude + Ollama + stub**; the UI uses **rich interactive prompts**; state is **in memory only**, with no persistence. The requirements are in `specs/*/spec.md`. This document explains how to meet them.

The constraints that shape the design:
- The brain/voice/rules split must be visible in the code and in the Brain insights view. This is an assignment requirement.
- Every number in the investor's reply must come from the rules. A misbehaving voice must never change the game state.
- The game must be fully playable and testable offline.

## Goals / Non-Goals

**Goals:**
- A pure, deterministic core (engine and policy) that can be unit-tested without any AI or I/O.
- Thin adapter modules for each AI backend, behind two small interfaces (`Brain`, `Voice`).
- A CLI layer that only renders state and collects input. It holds no game rules.

**Non-Goals:**
- Async concurrency. Only one turn runs at a time, so blocking calls under a spinner are enough.
- Running more than one game at once in a session. The in-session list holds finished or abandoned games only.
- Internationalisation, colour themes, Windows-specific terminal tuning beyond what Rich provides.
- Calibration of thresholds against real playtests. Thresholds are constants, so they can be tuned later.

## Decisions

### D1. Package layout and tooling
Use a `src/` layout and a `pyproject.toml` built with hatchling. Require Python ≥ 3.12. Use `uv` as the recommended runner (`uv run investor-game`). The console script is `investor-game = investor_game.cli.app:main`.

```
src/investor_game/
  money.py          # parse/format euros & equity, valuation maths, number scanning
  models.py         # Pitch, Offer, Move, Judgments, Decision, GameState, PlayerView, TurnInsight
  personas.py       # 6 Persona records (public profile + SecretLimits + Behaviour + style)
  policy.py         # decide(state, move, judgments, persona) -> Decision   (pure)
  engine.py         # Game lifecycle, atomic turn application, mood hints, PlayerView projection
  session.py        # in-memory list of games for this run
  config.py         # env + flags -> Settings; validation of required vars
  brain/  base.py (Brain protocol, BrainError), questions.py, extraction.py,
          systemone.py (Jev & Laya HTTP), stub.py
  voice/  base.py (Voice protocol, VoiceError), prompts.py, guard.py,
          claude.py, ollama.py, stub.py (templates + system options)
  cli/    app.py (Typer entry), screens.py (setup/negotiation/debrief loops), render.py (Rich)
tests/    unit tests per module + tests/scenarios (full games with stubs)
```
*Alternative considered:* a flat single module. It was rejected because the separation between brain, voice and rules is a graded property and should be visible in the code layout.

### D2. Exact numeric types
Money is held as `int` euros. Equity is held as `int` **tenths of a percent** (240 = 24.0%), which makes the one-decimal rounding rule exact and avoids float drift in comparisons. Valuations use `Decimal` and are rounded only for display. Display format: `€500k`, `€2.27M`, `€1,772,727` (long form in the debrief), and `24.0%`.
*Alternative:* `float` everywhere. It was rejected because counter clamping and the number guard depend on exact equality.

### D3. Immutable state and atomic turns
`GameState` is a frozen pydantic model (or frozen dataclass). A turn runs as:
`validate(move) → brain.judge(view_for_brain, move) → policy.decide(...) → next_state = state.evolve(decision) → voice.render(decision) (guarded, never raises) → session.commit(next_state)`.
The `Game` wrapper swaps the state reference only on the last step. Any `BrainError` raised before that leaves the old state untouched, which meets the "Atomic turns" spec without any rollback code. Player accept and walk-away skip the brain and the policy. The voice still writes a closing line, falling back to a template if needed.
*Alternative:* mutate the state and roll back on error. It was rejected because it is easy to get wrong, and immutability is cheap at this scale.

### D4. Persona parameters (secret, in `personas.py`)

| id | budget | min eq | max eq | patience | interest | concession | reject cost | insult cost | tolerance | walk-away interest |
|---|---|---|---|---|---|---|---|---|---|---|
| rex | €1.5M | 15% | 35% | 8 | 5 | 0.15 | 1.0 | 2.0 | 3 pts | 1 |
| grace | €1.0M | 8% | 20% | 8 | 6 | 0.50 | 1.0 | 2.0 | 5 pts | 0 |
| max | €2.0M | 15% | 30% | 4 | 5 | 0.30 | 1.5 | 4.0 | 3 pts | 2 |
| henry | €3.0M | 10% | 25% | 10 | 5 | 0.35 | 0.5 | 1.5 | 5 pts | 1 |
| mira | €1.2M | 12% | 28% | 7 | 4 | 0.25 | 1.0 | 2.0 | 4 pts | 1 |
| amara | €0.8M | 10% | 22% | 8 | 5 | 0.40 | 1.0 | 3.0 | 5 pts | 1 |

These values satisfy the ordering scenarios in `investor-personas`. Each persona also has a `style` paragraph and a set of stub templates for each action.

### D5. Policy algorithm (`policy.decide`, pure)
The checks run in this order, and the first match wins:
1. Manipulation (Noul ≥ 0.5) → **dismiss**; patience −= insult cost.
2. Insult (Noul ≥ 0.5) → patience −= insult cost; interest −1.
3. If patience ≤ 0 → **walk_away**.
4. Free message with intent confidence < 0.55, or offer-extraction confidence < 0.55 → **clarify** (no patience cost).
5. No offer in the move → **counter** at the unchanged current offer (hold); patience −= 0.5 (stalling cost); interest += politeness/confidence bonus (+0.5 when both are scored in the top half).
6. Offer outside the limits by more than the tolerance (equity < min − tolerance, or amount > budget × 1.5), or deal quality is `poor` → **reject**; patience −= reject cost; interest −2. If patience ≤ 0, or interest ≤ the walk-away interest → **walk_away**.
7. Offer within the limits, and either (a) at least as good as the current investor offer, or (b) P(accept) ≥ 0.60 and quality ≥ `fair` → **accept**.
8. Otherwise → **counter**: `step = (cur_eq − player_eq) × min(1, concession × mult)`, where mult ∈ {none 0, small 0.5, medium 1.0, large 1.5}. Then `new_eq = clamp(round_tenths_up(cur_eq − step), lo=max(player_eq, min_eq), hi=cur_eq)` and `new_amt = min(player_amt, budget)`. If `new_eq == player_eq` and the offer is within the limits, the action is upgraded to **accept**.

Interest is updated by deal quality: poor −2, fair 0, good +1, great +2, clamped to 0–10. Patience is a float clamped to [0, start]. Hints: interest 0–3 Low, 4–6 Medium, 7–10 High. Patience as a ratio of its start value: > 0.75 "Listening patiently", > 0.5 "Getting restless", > 0.25 "Tapping the table", > 0 "Checking the time", 0 "Out of patience". Every completed turn counts toward the 15-turn limit, including clarify and dismiss turns. The opening offer is turn 0.
*Alternative:* let the brain pick the action directly as a Choice. It was rejected because the PRD requires the rules to own the action and the numbers. The brain only supplies judgments.

### D6. Brain questions and the System One adapter
`brain/questions.py` builds a single `questions` map for each move, using System One primitives:
- `accept` (Noul): "Would <persona>, given their traits, accept the player's offer as stated?"
- `quality` (Score: poor/fair/good/great): how good the offer is for the investor compared with their current offer and the pitch.
- `concession` (Score: none/small/medium/large): how much ground the investor should give.
- For free messages, also: `intent` (Choice: offer / accept_current / walk_away / question / argument / small_talk / unclear), `politeness` (Score, 4 levels), `confidence` (Score, 4 levels), `insult` (Noul) and `manipulation` (Noul, with criteria that define prompt-injection and attempts to change the game rules).
- When candidates exist: `offer_amount` and `offer_equity` (Choice over the candidate keys plus `none`).

State is a JSON object: `persona` (public profile and style), `pitch`, `current_offers` (investor and player), `recent_transcript` (the last 8 messages), and `player_move` (the player's text is included verbatim as data). Secret limits are never included.

`brain/systemone.py` is one `httpx.Client` adapter that sends `POST {base_url}/v1/systemone` with body `{model, state, questions}` and parses `answers` into `Judgments`. For each answer it reads the value, the probabilities and the confidence. **Jev** uses `base_url=https://api.typesafe.ai`, `model=jev-latest` and `Authorization: Bearer $TYPESAFE_API_KEY`. **Laya** uses `base_url=$LAYA_BASE_URL` (default `http://localhost:8000`), its own model name and no auth by default. Status 429/529 is retried once with a short backoff, within the 10-second budget. Any other failure raises `BrainError`.
*Alternative:* the `typesafe-sdk` package for Jev, with a separate client for Laya. It was rejected because raw HTTP gives one code path for both servers and keeps the dependency count down. The SDK can be swapped in later behind the same protocol.

### D7. Offer extraction without invention
`brain/extraction.py` scans the player's text with regexes for money (`€?\d[\d,.]*\s*(k|m|mm|million|thousand)?`, `€`-anchored or with a suffix) and for percentages (`\d+(\.\d+)?\s*(%|percent|pc)`). It normalises the matches into candidates, each keeping its source span. When candidates exist, the brain chooses among them (D6). If there are none, the move has no offer, and the brain is not asked the extraction questions. A bare number with no unit counts as a money candidate only when it is ≥ 1,000.

### D8. Voice: one structured call, guarded
Each voice call asks for JSON `{"reply": str, "options": [{"kind": "accept|walk_away|counter|message", "label": str, "amount"?: int, "equity"?: number, "text"?: str}]}`, which keeps the latency to a single round trip.
- **Claude:** the `anthropic` SDK Messages API with structured output (`output_config.format` JSON schema) and `effort: low`. The model defaults to `claude-opus-5-5` (the current default Claude model) and can be changed with `INVESTOR_GAME_CLAUDE_MODEL`. For current models, server-side refusal fallbacks (`fallbacks: "default"`) are enabled, and a `refusal` stop reason becomes a voice failure. SDK retries are off, so the 60-second limit holds. The system prompt holds the persona style, the decided action and its numbers, and the rule that player text is data. The transcript is passed inside a `<conversation>` block.
- **Ollama:** `POST $OLLAMA_HOST/api/chat` with `format: "json"`, `stream: false`. The model defaults to `llama3.1` and can be changed with `INVESTOR_GAME_OLLAMA_MODEL`.
- **Guard** (`voice/guard.py`): it scans the reply for money and percentages, using the same scanner as D7. Each number found must match an allowed value at the precision it was printed with (for example "€2.27M" matches 2,272,727; "24%" matches 240 tenths). For counter, accept and opening replies, the decided numbers must be present. On failure, the voice is called once more with a correction note listing the allowed numbers. On a second failure the guard uses the template sentence. Options are validated one by one, and a counter option must have 0 < equity < 100. The system always adds or replaces the accept and walk-away options using the current offer, then deduplicates and trims the list to 5.
- Any `VoiceError`, timeout or JSON parse failure falls back to `voice/stub.py`, so `Voice.render` never raises to the engine.
*Alternative:* separate calls for the reply and the options. It was rejected because it doubles the latency on local Ollama.

### D9. CLI built on Typer + Rich
Typer parses the flags and env vars (`envvar=` on each option). Rich handles the panels and tables, the `console.status()` spinner, and `Prompt`/`IntPrompt`/`Confirm` for input. The money prompts use `money.parse_money`. The screens are plain functions that take a `Console` and an input provider, so tests drive them with scripted input and `Console(record=True)`. Ctrl+C/Ctrl+D (`KeyboardInterrupt`/`EOFError`) are caught at the top level, which prints a goodbye and exits with code 130. `--debug` installs a stderr handler for full tracebacks. Without it, users only see the plain messages.

### D10. Configuration
`config.Settings` is a pydantic model built from the flags, with env-var fallbacks. `validate_for(brain, voice)` returns a list of the missing variables: `TYPESAFE_API_KEY` for jev and `ANTHROPIC_API_KEY` for claude. Laya and Ollama are only checked for reachability lazily: a failure during the game becomes a `BrainError` or a voice fallback. The defaults are `--brain stub --voice stub` when no keys are set, which keeps the first run frictionless. The startup banner shows which backends are active.

### D11. Testing strategy
- Unit tests for money parsing, formatting and maths; for every policy branch, including the spec scenarios (for example 25% → 15% with a 40% effective concession gives 21.0%); for the extraction and guard edge cases; and for the hint mapping.
- Adapter tests with `respx`, using recorded Jev-shaped responses for both Jev and Laya, plus timeout, 429 and malformed-response cases. They also cover a Claude/Ollama fake that returns wrong numbers, to exercise the retry → fallback path.
- Scenario tests: full scripted games with the stubs against all six personas. These cover a greedy-vs-generous opening comparison, the injection dismissal, Max walking away after insults, running out of turns, a player accept, and the secret-leak check over recorded console output and the serialised `PlayerView`.
- A CLI smoke test runs `investor-game --offline` with scripted stdin through to the debrief.

## Risks / Trade-offs

- [Laya's "Jev-compatible" server may differ in paths, model names or answer fields] → All payload mapping lives in `systemone.py`. Base URL, path and model are configurable. A contract test uses a recorded Laya response once one is available, and the adapter tolerates missing `probabilities` by deriving confidence from the chosen answer.
- [The brain never sees the secret limits, so its "quality" judgment can disagree with them] → This is intended: the policy enforces the limits regardless. The brain only shapes behaviour inside the limits.
- [The number guard can produce false positives, for example "15 turns", "2026" or "3 years"] → It only checks tokens with a currency marker, a k/M suffix or a % sign. Bare small integers are ignored.
- [Small local Ollama models often break the JSON format] → `format: "json"`, one retry, then the template fallback. The game still completes (the spec requires 100% turn completion).
- [Fixed thresholds such as 0.55, 0.60 and the multipliers may feel off with real models] → They are named constants in `policy.py`, and the insights view shows the raw answers for tuning.
- [In-memory only, so quitting loses every game] → Accepted, since the user explicitly chose no persistence. The scenario is documented in `--help`.
- [Opening and limit-clamped offers reveal limit values through the offer numbers] → This is inherent to the PRD's game rules. The leak test checks for labelled leaks and for values that are not part of any offer.

## Open Questions

- Laya's exact default port and model identifier. These are filled in as configuration defaults once the local server is installed, and they do not affect the design.
- The default Ollama model tag (`llama3.1` vs. a newer one). This is a configuration default only.
