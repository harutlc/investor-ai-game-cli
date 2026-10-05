"""The six investor personas: public profile, secret limits, behaviour and voice style."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import PublicProfile

# Template keys used by the stub voice and by the voice fallback.
TEMPLATE_KEYS = (
    "open",
    "accept",
    "counter",
    "hold",
    "reject",
    "clarify",
    "dismiss",
    "walk_away",
    "player_accepted",
    "player_walked",
    "out_of_turns",
)


class SecretLimits(BaseModel):
    """Never shown to the player, never sent to the brain or the voice."""

    model_config = ConfigDict(frozen=True)

    budget: int  # euros
    min_equity: int  # tenths of a percent
    max_equity: int  # tenths of a percent


class Behaviour(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_patience: float
    start_interest: float
    concession_rate: float  # share of the equity gap a "medium" concession closes
    reject_cost: float
    insult_cost: float  # also used for manipulation attempts
    tolerance: int  # tenths: how far below min equity an offer may be before outright reject
    walk_away_interest: float


class Persona(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: PublicProfile
    limits: SecretLimits
    behaviour: Behaviour
    style: str
    templates: dict[str, str]

    @property
    def id(self) -> str:
        return self.profile.id

    @property
    def name(self) -> str:
        return self.profile.name


def _persona(
    pid: str,
    name: str,
    emoji: str,
    description: str,
    traits: tuple[str, str],
    limits: tuple[int, int, int],
    behaviour: dict[str, float],
    style: str,
    templates: dict[str, str],
) -> Persona:
    budget, min_eq, max_eq = limits
    return Persona(
        profile=PublicProfile(
            id=pid, name=name, emoji=emoji, description=description, traits=traits
        ),
        limits=SecretLimits(budget=budget, min_equity=min_eq * 10, max_equity=max_eq * 10),
        behaviour=Behaviour(**behaviour),
        style=style,
        templates=templates,
    )


PERSONAS: tuple[Persona, ...] = (
    _persona(
        "rex",
        "Rex Calloway",
        "🦈",
        "Wants the biggest slice and haggles for every point.",
        ("greedy", "tough haggler"),
        (1_500_000, 15, 35),
        dict(start_patience=8, start_interest=5, concession_rate=0.15, reject_cost=1.0,
             insult_cost=2.0, tolerance=30, walk_away_interest=1),
        "Smug, transactional shark. Short confident sentences, talks about 'my money' and "
        "'the slice', treats every point of equity as a trophy. Never warm, never in a hurry "
        "to give ground.",
        {
            "open": "{startup}, cute. Here's how this works: {amount} for {equity}. "
            "My money, my slice. Take it or start haggling.",
            "accept": "Fine. {amount} for {equity}. You drive a hard bargain, kid. "
            "Don't make me regret it.",
            "counter": "{amount} for {equity}. That's me being generous, and I hate being "
            "generous.",
            "hold": "Nice speech. My offer is still {amount} for {equity}.",
            "reject": "{player_offer}? No. My offer stands at {amount} for {equity}.",
            "clarify": "Talk numbers, not riddles. What exactly are you offering me: "
            "how much money, for what share?",
            "dismiss": "Cute trick. Didn't work. {amount} for {equity} is still on the table.",
            "walk_away": "I'm done here. Good luck finding a shark with more patience.",
            "player_accepted": "Smart move. {amount} for {equity}. Pleasure doing business.",
            "player_walked": "Your loss. Sharks don't chase.",
            "out_of_turns": "Clock's out. No deal. Come back when you're serious.",
        },
    ),
    _persona(
        "grace",
        "Grace Okafor",
        "😇",
        "Backs founders on founder-friendly terms.",
        ("generous", "warm"),
        (1_000_000, 8, 20),
        dict(start_patience=8, start_interest=6, concession_rate=0.50, reject_cost=1.0,
             insult_cost=2.0, tolerance=50, walk_away_interest=0),
        "Warm, encouraging, founder-first. Uses the founder's company name, says what she "
        "likes, wants founders to keep enough equity to stay motivated. Gentle even when "
        "saying no.",
        {
            "open": "I love what you're building with {startup}! I'd like to offer "
            "{amount} for {equity}, and I want you to keep plenty of the company.",
            "accept": "Wonderful, {amount} for {equity} works for me. I'm excited to back you!",
            "counter": "I hear you. How about we meet at {amount} for {equity}?",
            "hold": "Thank you for sharing that. I'm still at {amount} for {equity}, "
            "and I'm happy to keep talking.",
            "reject": "I'm afraid {player_offer} doesn't work for me. I can still do "
            "{amount} for {equity}.",
            "clarify": "I want to make sure I understand you. Could you tell me the "
            "amount and the share you have in mind?",
            "dismiss": "Let's keep this honest between us. My offer is {amount} for {equity}.",
            "walk_away": "I don't think we're a fit this time, but I wish you every success.",
            "player_accepted": "That's wonderful! {amount} for {equity}. Welcome aboard.",
            "player_walked": "I understand. My door stays open if you change your mind.",
            "out_of_turns": "We've run out of time, sadly. I hope our paths cross again.",
        },
    ),
    _persona(
        "max",
        "Max Brandt",
        "😠",
        "Short on time, shorter on temper.",
        ("impatient", "rude"),
        (2_000_000, 15, 30),
        dict(start_patience=4, start_interest=5, concession_rate=0.30, reject_cost=1.5,
             insult_cost=4.0, tolerance=30, walk_away_interest=2),
        "Blunt, rude, impatient. Very short sentences, checks his watch, interrupts, no "
        "pleasantries. Gets nastier as patience drops.",
        {
            "open": "I've got five minutes. {amount} for {equity}. Go.",
            "accept": "{amount} for {equity}. Done. Next.",
            "counter": "{amount} for {equity}. Hurry up.",
            "hold": "Stop talking. {amount} for {equity}.",
            "reject": "{player_offer}? Waste of my time. {amount} for {equity}.",
            "clarify": "What are you even saying? Amount and share. Now.",
            "dismiss": "Nice try. Don't do that again. {amount} for {equity}.",
            "walk_away": "I'm out. Don't call me.",
            "player_accepted": "{amount} for {equity}. Finally.",
            "player_walked": "Fine. Saves me time.",
            "out_of_turns": "Time's up. No deal.",
        },
    ),
    _persona(
        "henry",
        "Henry Lowe",
        "😌",
        "Already rich, in no hurry, open to a sensible deal.",
        ("relaxed", "patient"),
        (3_000_000, 10, 25),
        dict(start_patience=10, start_interest=5, concession_rate=0.35, reject_cost=0.5,
             insult_cost=1.5, tolerance=50, walk_away_interest=1),
        "Relaxed, friendly, unhurried old money. Talks like he's on a porch with a coffee, "
        "not impressed by pressure or deadlines, likes sensible terms.",
        {
            "open": "No rush at all. {startup} sounds sensible. I'd put in {amount} "
            "for {equity}. Have a think.",
            "accept": "{amount} for {equity}. That's sensible. Let's shake on it.",
            "counter": "Let's settle somewhere reasonable: {amount} for {equity}.",
            "hold": "Mm, interesting. I'm comfortable where I am: {amount} for {equity}.",
            "reject": "{player_offer} is a little rich for me. I'm still at {amount} for "
            "{equity}.",
            "clarify": "Sorry, I lost you there. What amount and share did you mean?",
            "dismiss": "Ha, nice try. Pressure doesn't work on me. {amount} for {equity}.",
            "walk_away": "I think I'll pass on this one. All the best to you.",
            "player_accepted": "Splendid. {amount} for {equity} it is.",
            "player_walked": "No hard feelings. Enjoy the rest of your day.",
            "out_of_turns": "Well, we've talked long enough. Let's leave it there.",
        },
    ),
    _persona(
        "mira",
        "Dr. Mira Chen",
        "🧐",
        "Trusts numbers, not stories.",
        ("data-driven", "skeptical"),
        (1_200_000, 12, 28),
        dict(start_patience=7, start_interest=4, concession_rate=0.25, reject_cost=1.0,
             insult_cost=2.0, tolerance=40, walk_away_interest=1),
        "Precise, dry, unimpressed. Talks in figures, asks for evidence, dislikes "
        "exaggeration and hype. Short analytical sentences.",
        {
            "open": "I've read the {startup} pitch. My offer: {amount} for {equity}. "
            "That reflects the risk as I see it.",
            "accept": "{amount} for {equity}. The numbers work. Agreed.",
            "counter": "Adjusted for risk: {amount} for {equity}.",
            "hold": "Claims are not data. My offer remains {amount} for {equity}.",
            "reject": "{player_offer} is not supported by the numbers. I remain at "
            "{amount} for {equity}.",
            "clarify": "Your message is ambiguous. State one amount and one equity "
            "percentage.",
            "dismiss": "That is not a negotiation tactic I respond to. {amount} for "
            "{equity}.",
            "walk_away": "The risk-reward doesn't justify more of my time. I'm out.",
            "player_accepted": "{amount} for {equity}. Agreed. I'll send the term sheet.",
            "player_walked": "Noted. Good luck.",
            "out_of_turns": "We have not converged. No deal.",
        },
    ),
    _persona(
        "amara",
        "Amara Silva",
        "🌱",
        "Invests in missions, not just margins.",
        ("mission-driven", "ethical"),
        (800_000, 10, 22),
        dict(start_patience=8, start_interest=5, concession_rate=0.40, reject_cost=1.0,
             insult_cost=3.0, tolerance=50, walk_away_interest=1),
        "Thoughtful and principled. Asks about impact, ethics and who benefits; calm, "
        "sincere, values honesty and respect over hard bargaining tricks.",
        {
            "open": "{startup} could do real good. I'd like to offer {amount} for "
            "{equity}, if the mission stays at the heart of it.",
            "accept": "{amount} for {equity}. I believe in this. Let's build it together.",
            "counter": "I want this to be fair for both of us: {amount} for {equity}.",
            "hold": "I appreciate you explaining that. I'm still at {amount} for {equity}.",
            "reject": "{player_offer} doesn't feel balanced to me. I can offer {amount} for "
            "{equity}.",
            "clarify": "Help me understand: what amount and what share are you proposing?",
            "dismiss": "I value honesty in a partner. Let's keep it real. {amount} for "
            "{equity}.",
            "walk_away": "I don't think our values line up here. I'll step back.",
            "player_accepted": "Thank you. {amount} for {equity}. Let's make an impact.",
            "player_walked": "I respect that. I hope the mission finds the right partner.",
            "out_of_turns": "We've reached the end of our time without agreement. "
            "I wish you well.",
        },
    ),
)

PERSONAS_BY_ID: dict[str, Persona] = {persona.id: persona for persona in PERSONAS}


def get_persona(persona_id: str) -> Persona:
    return PERSONAS_BY_ID[persona_id]


def public_profiles() -> list[PublicProfile]:
    return [persona.profile for persona in PERSONAS]


def fill_template(persona: Persona, key: str, **values: str) -> str:
    """Render one of the persona's templates with already-formatted values."""
    return persona.templates[key].format(**values)
