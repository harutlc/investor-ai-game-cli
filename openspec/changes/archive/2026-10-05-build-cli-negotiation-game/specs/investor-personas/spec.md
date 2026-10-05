## Purpose

Defines the six investor personalities a player can negotiate against. Each one has a public profile, secret deal limits, behaviour settings that shape decisions, and a speaking style that shapes how the investor talks.

## ADDED Requirements

### Requirement: Six fixed personas
The system SHALL provide exactly six investor personas: Rex Calloway 🦈 ("Wants the biggest slice and haggles for every point."; traits greedy, tough haggler), Grace Okafor 😇 ("Backs founders on founder-friendly terms."; generous, warm), Max Brandt 😠 ("Short on time, shorter on temper."; impatient, rude), Henry Lowe 😌 ("Already rich, in no hurry, open to a sensible deal."; relaxed, patient), Dr. Mira Chen 🧐 ("Trusts numbers, not stories."; data-driven, skeptical) and Amara Silva 🌱 ("Invests in missions, not just margins."; mission-driven, ethical). Each persona SHALL have a stable identifier, a display name, an emoji, a one-line description and exactly two visible traits.

#### Scenario: Listing personas
- **WHEN** the persona catalogue is requested
- **THEN** it returns six personas in the order Rex, Grace, Max, Henry, Mira, Amara, each with an id, name, emoji, description and two traits

### Requirement: Secret limits per persona
Each persona SHALL have secret limits: a maximum budget in euros, a minimum acceptable equity percentage and a maximum desired equity percentage, with 0 < minimum equity < maximum equity < 100. These limits SHALL NOT be part of the public profile.

#### Scenario: Public profile excludes secrets
- **WHEN** a persona's public profile is produced for display
- **THEN** it contains no budget, minimum equity, maximum equity, interest or patience values

#### Scenario: Limits are internally consistent
- **WHEN** any persona's secret limits are loaded
- **THEN** budget > 0 and 0 < min equity < max equity < 100

### Requirement: Behaviour parameters differ by persona
Each persona SHALL have behaviour parameters: starting patience, starting interest, a concession rate that controls how far a counter-offer moves toward the player, a patience cost for rejections, a patience cost for insults or manipulation, and a threshold for walking away. The values SHALL be chosen so that Rex concedes in smaller steps than Grace, Max has the lowest starting patience and the highest insult cost, Henry has the highest starting patience, and Rex's maximum desired equity is higher than Grace's.

#### Scenario: Greedy vs generous opening
- **WHEN** the same pitch is opened against Rex and against Grace
- **THEN** Rex's opening equity is strictly higher than Grace's

#### Scenario: Concession ordering
- **WHEN** Rex and Grace each counter the same player offer from the same state
- **THEN** Grace's counter moves at least as far toward the player's equity as Rex's does, and strictly further when neither counter is clamped by a limit

### Requirement: Voice style per persona
Each persona SHALL have a written voice style (tone, vocabulary, attitude) that is given to the voice AI and used by the template stub, so that replies read in that persona's character.

#### Scenario: Style is applied
- **WHEN** a reply is generated for Max Brandt
- **THEN** the voice request includes Max's style description (blunt, rude, impatient)
