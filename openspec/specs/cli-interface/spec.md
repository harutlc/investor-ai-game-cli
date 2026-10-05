# cli-interface Specification

## Purpose

Defines the terminal experience of the game, which is a single interactive command. It covers the Setup, Negotiation and Debrief steps, the three ways to reply, the deal panel and mood hints, the Brain insights view, the list of games played in the current run, configuration, and safe error handling.

## Requirements

### Requirement: Single interactive command
The system SHALL install a console command `investor-game` that starts an interactive session in the terminal. It SHALL need no server, browser or database. The session SHALL show the current step as "Setup → Negotiation → Debrief", with the active step highlighted. The program SHALL work with the keyboard only, and SHALL exit cleanly on Ctrl+C or Ctrl+D with a short goodbye and no stack trace.

#### Scenario: Start the game
- **WHEN** the user runs `investor-game --offline`
- **THEN** the Setup step is shown with the six investors

#### Scenario: Interrupt
- **WHEN** the user presses Ctrl+C at any prompt
- **THEN** the program exits with a goodbye message and exit code 130, without a traceback

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

### Requirement: Setup step
The Setup step SHALL list the six investors with their number, emoji, name, description and traits, and let the player choose one by number. It SHALL then ask for the startup name, sector, description, pre-money valuation and ask, with the GreenCharge example as the default for each prompt (Enter accepts it). Money inputs SHALL accept forms such as `500000`, `500k`, `2M` and `€2,000,000`. After the valuation and the ask are entered, the screen SHALL show the implied equity ("Asking €500k at €2M pre-money = 20.0% equity"). Invalid fields SHALL show the plain-language error and ask for that field again. The player SHALL confirm before the negotiation starts.

#### Scenario: Accept defaults
- **WHEN** the player picks investor 1 and presses Enter on every pitch prompt
- **THEN** the pitch is GreenCharge / EV charging / €2M valuation / €500k ask, and the implied equity of 20.0% is shown

#### Scenario: Invalid valuation
- **WHEN** the player types "lots" for the valuation
- **THEN** an error explains that it must be a whole number of euros above zero, and the valuation prompt repeats

### Requirement: Negotiation step display
During negotiation, after each investor reply, the screen SHALL show: the investor's message (with emoji and name), a deal panel (the investor's current offer with implied pre-money, the player's last offer if any, the gap in equity points and in money, and "Turn N of 15"), and mood hints ("Interest: Medium", "Patience: Getting restless") with the note "Hints only. The real numbers stay hidden." A spinner with "<Name> is thinking…" SHALL be shown while a turn is processed. No other input SHALL be accepted until the turn finishes.

#### Scenario: Deal panel after counter
- **WHEN** the investor counters with €550,000 for 24% after the player offered €550,000 for 18%
- **THEN** the deal panel shows both offers, a gap of 6.0 points, and the turn count

### Requirement: Three ways to reply
Each turn the player SHALL be shown the numbered suggested options, plus the commands `o` (make an offer), `m` (write a message), `i` (Brain insights), `h` (help) and `q` (quit the game, treated as walk away after confirmation). Choosing an option number SHALL send that option. With `o`, the player SHALL enter the amount and then the equity percentage. The screen SHALL show the implied pre- and post-money valuation and ask for confirmation before sending. With `m`, the player SHALL type a free message of up to 4,000 characters.

#### Scenario: Precise offer preview
- **WHEN** the player chooses `o`, enters 500k and 15
- **THEN** the screen shows "€500k for 15.0% → €3.33M post-money, €2.83M pre-money" and asks to confirm before sending

#### Scenario: Pick an option
- **WHEN** the player types the number of the "Walk away" option
- **THEN** the game ends with "You walked away"

### Requirement: Brain insights view
The `i` command SHALL show, for each completed turn, the questions the brain was asked, the answers, the probability or confidence as a percentage, an "uncertain" marker for low confidence, the chosen investor action, the brain backend name and the elapsed time. It SHALL NOT show secret limits or numeric interest or patience.

#### Scenario: View insights
- **WHEN** the player types `i` after two turns
- **THEN** a table for each of the two turns is shown with questions, answers, confidence, backend and latency

### Requirement: End banner and Debrief step
When the game ends, a banner SHALL announce "Deal closed" or "Negotiation over". The Debrief SHALL show the headline (**Deal closed**, or **No deal** with the reason: "<Name> walked away", "You walked away" or "Out of turns") and the turns used. After a deal it SHALL show the investment, the equity, and the post-money and pre-money values, with pre-money compared with the valuation the player asked for (difference in euros and percent). Without a deal it SHALL show "Where it stopped" with the investor's last offer and the player's last offer. It SHALL then offer: read the conversation again, view Brain insights, play again, list your games, or quit. The Debrief SHALL NOT reveal secret limits.

#### Scenario: Deal debrief
- **WHEN** the game ends with a deal at €500,000 for 22%
- **THEN** the debrief shows post-money €2.27M and pre-money €1.77M, and compares €1.77M with the €2M asked (−€227k, −11.4%)

#### Scenario: No-deal debrief
- **WHEN** Max walks away
- **THEN** the headline is "No deal — Max Brandt walked away", and the "Where it stopped" section shows both last offers

### Requirement: Games in this run
The Setup step and the Debrief SHALL offer a "Your games" list of games played in the current run, newest first, each with investor, startup, outcome and turns. Choosing one SHALL show its transcript and debrief (read-only). The list SHALL be empty when the program starts.

#### Scenario: Reopen earlier game
- **WHEN** the player has finished two games and opens "Your games"
- **THEN** both are listed newest first, and choosing one shows its transcript and debrief

### Requirement: Safe errors
Errors shown to the player SHALL be short and plain (for example "The investor couldn't respond. Your move wasn't used. Try again."). They SHALL NOT include stack traces, URLs, API keys or raw service responses. A `--debug` flag SHALL allow detailed errors to be printed to stderr for developers.

#### Scenario: Brain failure message
- **WHEN** the brain request fails during a turn
- **THEN** the player sees the plain retry message, and is prompted again for the same turn

### Requirement: Log folder shown to the player
When LLM call logging is enabled, the startup banner SHALL say that logging is on and name the log directory. The Negotiation step SHALL show the current game's log folder path when the game starts, and the Debrief SHALL show it again. When logging is off, no log paths SHALL be shown.

#### Scenario: Logging on
- **WHEN** the player starts a game with `--log-dir logs`
- **THEN** the negotiation screen shows a line such as "LLM logs: logs/2026-10-05T11-42-07_g1_rex", and the debrief shows the same path

#### Scenario: Logging off
- **WHEN** the player starts a game without a log directory
- **THEN** no "LLM logs" line is shown

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
