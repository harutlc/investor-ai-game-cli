"""Rich renderables built from ``PlayerView``s. No game rules live here."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models import Message, Offer, Option, Outcome, PlayerView, PublicProfile
from ..money import format_equity, format_money, format_percent, post_money, pre_money

STEPS = ("Setup", "Negotiation", "Debrief")


def steps(active: str) -> Text:
    text = Text()
    for i, step in enumerate(STEPS):
        if i:
            text.append(" → ", style="dim")
        text.append(step, style="bold reverse" if step == active else "dim")
    return text


def investors_table(profiles: list[PublicProfile]) -> Table:
    table = Table(title="Choose your investor", show_lines=False, expand=False)
    table.add_column("#", justify="right", style="bold")
    table.add_column("Investor")
    table.add_column("Description")
    table.add_column("Traits", style="cyan")
    for i, profile in enumerate(profiles, 1):
        table.add_row(str(i), f"{profile.emoji} {profile.name}", profile.description,
                      ", ".join(profile.traits))
    return table


def offer_line(offer: Offer | None) -> str:
    if offer is None:
        return "—"
    return (f"{format_money(offer.amount)} for {format_equity(offer.equity, fixed=True)} "
            f"(pre-money {format_money(offer.pre_money)})")


def offer_preview(amount: int, equity: int) -> str:
    return (f"{format_money(amount)} for {format_equity(equity, fixed=True)} → "
            f"{format_money(post_money(amount, equity))} post-money, "
            f"{format_money(pre_money(amount, equity))} pre-money")


def investor_message(view: PlayerView, message: Message) -> Panel:
    return Panel(message.text, title=f"{view.investor.emoji} {view.investor.name}",
                 title_align="left", border_style="magenta")


def player_message(message: Message) -> Panel:
    return Panel(message.text, title="You", title_align="right", border_style="blue")


def conversation(view: PlayerView) -> Group:
    return Group(*[
        investor_message(view, m) if m.role == "investor" else player_message(m)
        for m in view.transcript
    ])


def latest_investor_messages(view: PlayerView) -> list[Message]:
    """Investor messages after the player's last move (one, or two at the end)."""
    latest: list[Message] = []
    for message in reversed(view.transcript):
        if message.role != "investor":
            break
        latest.insert(0, message)
    return latest


def deal_panel(view: PlayerView) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row(f"{view.investor.first_name}'s offer", offer_line(view.investor_offer))
    table.add_row("Your last offer", offer_line(view.player_offer))
    if view.equity_gap is not None and view.amount_gap is not None:
        gap = f"{abs(view.equity_gap) / 10:.1f} points"
        if view.amount_gap:
            direction = "more" if view.amount_gap > 0 else "less"
            gap += f", you ask {format_money(abs(view.amount_gap))} {direction}"
        table.add_row("Gap", gap)
    table.add_row("Turn", f"Turn {view.turn} of {view.max_turns}")
    return Panel(table, title="Deal", title_align="left", border_style="green")


def mood_panel(view: PlayerView) -> Panel:
    body = Text()
    body.append("Interest: ", style="bold")
    body.append(f"{view.interest_hint}\n")
    body.append("Patience: ", style="bold")
    body.append(f"{view.patience_hint}\n")
    body.append("Hints only. The real numbers stay hidden.", style="dim italic")
    return Panel(body, title="Mood", title_align="left", border_style="yellow")


def options_table(options: tuple[Option, ...]) -> Table:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold")
    table.add_column()
    for i, option in enumerate(options, 1):
        label = option.label
        if option.kind == "message" and option.text and option.text != option.label:
            label = f"{option.label} [dim]— “{option.text}”[/dim]"
        table.add_row(f"{i}.", label)
    return table


COMMANDS_HELP = (
    "[bold]o[/bold] make an offer · [bold]m[/bold] write a message · "
    "[bold]i[/bold] Brain insights · [bold]h[/bold] help · [bold]q[/bold] quit (walk away)"
)

HELP_TEXT = """\
[bold]How to reply[/bold]
  • Type an option number to send that suggested reply.
  • [bold]o[/bold]: make a precise offer (amount, then equity %). You'll see the valuation first.
  • [bold]m[/bold]: write anything (up to 4,000 characters), including an offer in words.
  • [bold]i[/bold]: see how the investor's brain judged each turn.
  • [bold]q[/bold]: walk away from the deal.
Every offer is money for a share of the company. €500k for 20% means €2.5M post-money,
€2M pre-money. The game lasts at most 15 turns."""


def insights(view: PlayerView) -> RenderableType:
    if not view.insights:
        return Text("No turns yet: Brain insights appear after your first move.", style="dim")
    parts: list[RenderableType] = []
    for insight in view.insights:
        table = Table(title=f"Turn {insight.turn}: {insight.move}", title_justify="left",
                      expand=False)
        table.add_column("Question")
        table.add_column("Answer", style="cyan")
        table.add_column("Confidence", justify="right")
        table.add_column("")
        for answer in insight.answers:
            confidence = format_percent(Decimal(str(answer.confidence)) * 100, 0)
            if answer.kind == "noul":
                confidence += " yes"
            table.add_row(answer.question, answer.value, confidence,
                          "[yellow]uncertain[/yellow]" if answer.uncertain else "")
        if not insight.answers:
            table.add_row("(no brain call: the rules handle this move)", "", "", "")
        table.caption = (
            f"Action: {insight.action.value.replace('_', ' ')} · Brain: {insight.backend} "
            f"({insight.latency_ms} ms) · Voice: {insight.voice}"
        )
        parts.append(table)
    return Group(*parts)


def headline(view: PlayerView) -> str:
    if view.outcome is Outcome.DEAL:
        return "Deal closed"
    reasons = {
        Outcome.INVESTOR_WALKED: f"{view.investor.name} walked away",
        Outcome.PLAYER_WALKED: "You walked away",
        Outcome.OUT_OF_TURNS: "Out of turns",
    }
    return f"No deal — {reasons[view.outcome]}" if view.outcome else "In progress"


def end_banner(view: PlayerView) -> Panel:
    deal = view.outcome is Outcome.DEAL
    return Panel(Text("Deal closed" if deal else "Negotiation over", justify="center",
                      style="bold"), border_style="green" if deal else "red")


def debrief(view: PlayerView) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    if view.outcome is Outcome.DEAL and view.final_offer is not None:
        deal = view.final_offer
        diff = deal.pre_money - view.pitch.valuation
        percent = diff / view.pitch.valuation * 100
        sign = "+" if diff >= 0 else "−"
        table.add_row("Investment", format_money(deal.amount))
        table.add_row("Equity", format_equity(deal.equity, fixed=True))
        table.add_row("Post-money", format_money(deal.post_money))
        table.add_row(
            "Pre-money",
            f"{format_money(deal.pre_money)} vs {format_money(view.pitch.valuation)} asked "
            f"({sign}{format_money(abs(diff))}, {sign}{abs(percent):.1f}%)",
        )
    else:
        table.add_row("Where it stopped", "")
        table.add_row(f"  {view.investor.first_name}'s last offer", offer_line(view.investor_offer))
        table.add_row("  Your last offer", offer_line(view.player_offer))
    table.add_row("Turns used", f"{view.turn} of {view.max_turns}")
    return Panel(table, title=headline(view), title_align="left",
                 border_style="green" if view.outcome is Outcome.DEAL else "red")


def games_table(views: list[PlayerView]) -> Table:
    table = Table(title="Your games (this run)")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Investor")
    table.add_column("Startup")
    table.add_column("Outcome")
    table.add_column("Turns", justify="right")
    for i, view in enumerate(views, 1):
        table.add_row(str(i), f"{view.investor.emoji} {view.investor.name}", view.pitch.name,
                      headline(view), str(view.turn))
    return table
