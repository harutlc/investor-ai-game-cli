# game-engine Specification

## Purpose

Owns the lifecycle of a single negotiation game held in memory. It creates a game from a pitch and a persona, makes the opening offer, applies turns all-or-nothing, does the valuation maths, maps hidden moods to hints, and ends the game.

## Requirements

### Requirement: Pitch validation
The system SHALL accept a pitch with: startup name (1–80 characters after trimming), sector (1–60), description (1–2,000), pre-money valuation (whole euros, > 0) and ask (whole euros, > 0). Invalid input SHALL be rejected with a per-field, plain-language error message, and no game SHALL be created.

#### Scenario: Valid pitch
- **WHEN** a pitch "GreenCharge", "EV charging", a description, valuation 2,000,000 and ask 500,000 is submitted
- **THEN** it is accepted

#### Scenario: Name too long
- **WHEN** a startup name of 81 characters is submitted
- **THEN** the pitch is rejected with an error for the name field stating the 80-character limit

#### Scenario: Non-positive money
- **WHEN** the ask is 0 or negative, or not a whole number
- **THEN** the pitch is rejected with an error for the ask field stating it must be a whole number of euros above zero

### Requirement: Valuation maths
For any offer of amount A for equity E%, the system SHALL compute post-money = A / (E/100) and pre-money = post-money − A. The equity implied by the player's ask at their valuation SHALL be computed as ask / (valuation + ask) × 100. Money SHALL be displayed in euros with thousands separators or k/M shorthand. Equity SHALL be displayed with at most one decimal place.

#### Scenario: Implied valuation
- **WHEN** the offer is €500,000 for 20%
- **THEN** post-money is €2,500,000 and pre-money is €2,000,000

#### Scenario: Implied ask equity
- **WHEN** the valuation is €2,000,000 and the ask is €500,000
- **THEN** the implied equity is 20.0%

### Requirement: Opening offer
When a game starts, the investor SHALL make an opening offer of min(ask, persona budget) euros for the persona's maximum desired equity. The opening offer SHALL be written by the voice in the persona's style.

#### Scenario: Ask within budget
- **WHEN** the ask is €500,000 and the persona budget is €1,000,000
- **THEN** the opening offer amount is €500,000 at the persona's maximum equity

#### Scenario: Ask above budget
- **WHEN** the ask is €3,000,000 and the persona budget is €1,000,000
- **THEN** the opening offer amount is €1,000,000

### Requirement: Player moves
On each turn the system SHALL accept exactly one player move of one of these kinds: choosing a suggested option, a structured offer (amount > 0 euros and equity strictly between 0 and 100), a free message (1–4,000 characters), accepting the investor's current offer, or walking away. A move that fails validation SHALL be rejected with a plain message, and it SHALL NOT use up a turn.

#### Scenario: Structured offer out of range
- **WHEN** the player submits an offer with equity 0 or 100 or above
- **THEN** the move is rejected with a validation message and the turn count is unchanged

#### Scenario: Overlong message
- **WHEN** the player submits a free message longer than 4,000 characters
- **THEN** the move is rejected and the turn count is unchanged

### Requirement: Atomic turns
A turn SHALL be applied all-or-nothing. If the brain fails (error or timeout), the game state (offers, moods, turn count, transcript, insights) SHALL stay exactly as it was before the move. The player SHALL be told the investor could not respond and that they can try again. A voice failure SHALL NOT fail the turn (see investor-voice).

#### Scenario: Brain down
- **WHEN** the brain backend raises an error while a turn is processed
- **THEN** the game state equals its pre-move state, and the player sees a retryable error with no internal details

### Requirement: Turn limit
A game SHALL last at most 15 turns. A turn is one player move plus the investor's response. When the 15th turn completes without a deal or walk-away, the game SHALL end with outcome "Out of turns".

#### Scenario: Running out of turns
- **WHEN** the 15th turn ends with a counter-offer
- **THEN** the game ends with outcome "Out of turns"

### Requirement: End conditions
A game SHALL end with exactly one outcome: **Deal** (the player accepts the investor's current offer, or the investor accepts the player's offer), **Investor walked away** (the investor's action is walk away, or patience reaches zero), **You walked away** (the player chooses walk away), or **Out of turns**. The final terms of a Deal SHALL be the offer that was accepted.

#### Scenario: Player accepts
- **WHEN** the investor's current offer is €550,000 for 24% and the player accepts
- **THEN** the game ends as Deal with terms €550,000 for 24%

#### Scenario: Patience exhausted
- **WHEN** a turn reduces the investor's patience to zero
- **THEN** the game ends as Investor walked away

### Requirement: Finished games are read-only
Any move submitted to a finished game SHALL be refused with the message "This game has already ended", and it SHALL NOT change the game.

#### Scenario: Move after deal
- **WHEN** the player submits an offer to a game that ended in a Deal
- **THEN** the move is refused with "This game has already ended"

### Requirement: Mood hints
The system SHALL expose the investor's interest only as Low, Medium or High, and patience only as one of "Listening patiently", "Getting restless", "Tapping the table", "Checking the time", "Out of patience" (from most to least). The real numeric values SHALL NOT be exposed outside the engine and policy.

#### Scenario: Hint mapping
- **WHEN** patience is zero
- **THEN** the patience hint is "Out of patience"

### Requirement: Player-visible view hides secrets
Every view of a game shown to the player (deal panel, transcript, debrief, insights) SHALL be built from a player-safe projection. This projection SHALL NOT contain the persona's budget, minimum or maximum equity, or numeric interest or patience. An investor offer is public, even when its numbers happen to equal a limit (for example, the opening offer is made at the maximum equity). Such an offer SHALL never be labelled or described as a limit. An automated test SHALL play a full game with the stubs and assert that no secret value leaks.

#### Scenario: Full game leak check
- **WHEN** a complete game is played against each persona using the stub brain and voice, with the ask set below the budget and the scripted player offers kept above the minimum equity (so that no offer equals a limit), and all output is captured
- **THEN** the captured output contains neither the persona's budget nor its minimum equity value, and contains no numeric interest or patience values

#### Scenario: Projection has no secret fields
- **WHEN** the player-safe projection of any game is serialised
- **THEN** it has no fields for budget, minimum equity, maximum equity, interest or patience

### Requirement: In-memory games only
Games SHALL be kept only in process memory. The system SHALL keep a list of the games played during the current run, newest first. It SHALL NOT write game data to disk, and all games SHALL be discarded when the program exits.

#### Scenario: No files written
- **WHEN** a full game is played and the program exits
- **THEN** no game data files have been created
