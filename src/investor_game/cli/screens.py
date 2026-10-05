"""Interactive Setup → Negotiation → Debrief loop. Talks to the game only via ``Session``."""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console
from rich.markup import escape
from rich.rule import Rule

from ..models import (
    EXAMPLE_PITCH,
    BrainUnavailableError,
    GameOverError,
    Move,
    MoveError,
    Pitch,
    PitchError,
    PlayerView,
    validate_money_field,
    validate_text_field,
)
from ..money import format_money, implied_equity, parse_equity, parse_money
from ..personas import public_profiles
from ..session import Session
from . import render


class Terminal:
    """Console output plus line input. Tests swap in ``ScriptedTerminal``."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def ask(self, prompt: str, default: str | None = None) -> str:
        suffix = f" [dim]({escape(default)})[/dim]" if default else ""
        answer = self.console.input(f"[bold]{escape(prompt)}[/bold]{suffix}: ").strip()
        return answer or (default or "")


class ScriptedTerminal(Terminal):
    """Answers prompts from a list; raises ``EOFError`` when the script runs out."""

    def __init__(self, answers: Iterable[str], console: Console | None = None):
        super().__init__(console or Console(record=True, width=120, force_terminal=False))
        self.answers = list(answers)

    def ask(self, prompt: str, default: str | None = None) -> str:
        if not self.answers:
            raise EOFError
        answer = self.answers.pop(0)
        self.console.print(f"{prompt}: {answer}", markup=False, highlight=False)
        return answer.strip() or (default or "")


def confirm(term: Terminal, prompt: str, default: bool = True) -> bool:
    while True:
        answer = term.ask(f"{prompt} [{'Y/n' if default else 'y/N'}]").lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        term.console.print("Please answer y or n.")


class App:
    def __init__(self, term: Terminal, session: Session, backends: str = ""):
        self.term = term
        self.console = term.console
        self.session = session
        self.backends = backends
        self._warned: set[int] = set()  # games whose log warning was already shown

    # -- top level ----------------------------------------------------------

    def run(self) -> None:
        self.console.print(
            f"[bold]💼 Investor Negotiation Game[/bold]  [dim]{escape(self.backends)}[/dim]",
            soft_wrap=True,
        )
        while True:
            view = self.setup()
            if view is None:
                return
            view = self.negotiate(view)
            if not self.debrief(view):
                return

    # -- setup --------------------------------------------------------------

    def setup(self) -> PlayerView | None:
        self.console.print(Rule())
        self.console.print(render.steps("Setup"))
        profiles = public_profiles()
        while True:
            self.console.print(render.investors_table(profiles))
            choice = self.term.ask("Choose an investor (1-6), g = your games, q = quit").lower()
            if choice == "q":
                return None
            if choice == "g":
                self.your_games()
                continue
            if choice.isdigit() and 1 <= int(choice) <= len(profiles):
                profile = profiles[int(choice) - 1]
                break
            self.console.print("[red]Type a number from 1 to 6.[/red]")
        self.console.print(f"You chose {profile.emoji} [bold]{profile.name}[/bold].")
        self.console.print("[bold]Your pitch[/bold] [dim](press Enter to keep the example)[/dim]")

        name = self._ask_text("name", "Startup name")
        sector = self._ask_text("sector", "Sector")
        description = self._ask_text("description", "Description")
        valuation = self._ask_money("valuation", "Pre-money valuation (€)")
        ask = self._ask_money("ask", "Amount to raise (€)")
        self.console.print(
            f"Asking {format_money(ask)} at {format_money(valuation)} pre-money = "
            f"[bold]{implied_equity(ask, valuation):.1f}% equity[/bold]"
        )
        try:
            pitch = Pitch.create(name=name, sector=sector, description=description,
                                 valuation=valuation, ask=ask)
        except PitchError as exc:  # already validated field by field; defensive
            for message in exc.errors.values():
                self.console.print(f"[red]{escape(message)}[/red]")
            return self.setup()
        if not confirm(self.term, f"Start negotiating with {profile.name}?"):
            return self.setup()
        with self.console.status(f"{profile.name} is reading your pitch…"):
            return self.session.new_game(pitch, profile.id)

    def _ask_text(self, field: str, label: str) -> str:
        while True:
            value = self.term.ask(label, str(EXAMPLE_PITCH[field]))
            try:
                return validate_text_field(field, value)
            except ValueError as exc:
                self.console.print(f"[red]{escape(str(exc))}[/red]")

    def _ask_money(self, field: str, label: str) -> int:
        while True:
            value = self.term.ask(label, str(EXAMPLE_PITCH[field]))
            try:
                return validate_money_field(field, value)
            except ValueError as exc:
                self.console.print(f"[red]{escape(str(exc))}[/red]")

    # -- negotiation --------------------------------------------------------

    def negotiate(self, view: PlayerView) -> PlayerView:
        self.console.print(Rule())
        self.console.print(render.steps("Negotiation"))
        self.console.print(
            f"Negotiating {escape(view.pitch.name)} with {view.investor.emoji} "
            f"[bold]{view.investor.name}[/bold]. Type [bold]h[/bold] for help."
        )
        self.show_log_folder(view)
        self.show_turn(view)
        while not view.ended:
            move = self.read_move(view)
            if move is None:
                continue
            view = self.send(view, move)
        self.console.print(render.end_banner(view))
        return view

    def show_log_folder(self, view: PlayerView) -> None:
        if view.log_folder:
            # No wrapping, so the path stays copyable.
            self.console.print(f"[dim]LLM logs: {escape(view.log_folder)}[/dim]",
                               soft_wrap=True)
        self.show_log_warning(view)

    def show_log_warning(self, view: PlayerView) -> None:
        if view.log_warning and view.id not in self._warned:
            self._warned.add(view.id)
            self.console.print(f"[yellow]{escape(view.log_warning)}[/yellow]")

    def show_turn(self, view: PlayerView) -> None:
        for message in render.latest_investor_messages(view):
            self.console.print(render.investor_message(view, message))
        if view.ended:
            return
        self.console.print(render.deal_panel(view))
        self.console.print(render.mood_panel(view))
        self.console.print("[bold]Your options[/bold]")
        self.console.print(render.options_table(view.options))
        self.console.print(render.COMMANDS_HELP)

    def read_move(self, view: PlayerView) -> Move | None:
        choice = self.term.ask("Your move").strip()
        lower = choice.lower()
        if lower.isdigit() and 1 <= int(lower) <= len(view.options):
            return view.options[int(lower) - 1].to_move()
        if lower == "o":
            return self.make_offer(view)
        if lower == "m":
            text = self.term.ask("Your message (up to 4,000 characters)")
            return Move.message(text) if text.strip() else None
        if lower == "i":
            self.console.print(render.insights(view))
            return None
        if lower == "h":
            self.console.print(render.HELP_TEXT)
            return None
        if lower == "q":
            if confirm(self.term, "Walk away from this deal?", default=False):
                return Move.walk_away()
            return None
        self.console.print(
            f"[red]Type an option number (1-{len(view.options)}), o, m, i, h or q.[/red]"
        )
        return None

    def make_offer(self, view: PlayerView) -> Move | None:
        current = view.investor_offer
        while True:
            raw = self.term.ask("Amount (€)", format_money(current.amount))
            try:
                amount = parse_money(raw)
                break
            except ValueError:
                self.console.print("[red]The amount must be a whole number of euros above "
                                   "zero, e.g. 500k or 1.2M.[/red]")
        while True:
            raw = self.term.ask("Equity (%)")
            try:
                equity = parse_equity(raw)
                break
            except ValueError as exc:
                self.console.print(f"[red]{escape(str(exc))}.[/red]")
        self.console.print(render.offer_preview(amount, equity))
        if not confirm(self.term, f"Send this offer to {view.investor.first_name}?"):
            return None
        return Move.make_offer(amount, equity)

    def send(self, view: PlayerView, move: Move) -> PlayerView:
        try:
            with self.console.status(f"{view.investor.name} is thinking…"):
                new_view = self.session.play(view.id, move)
        except MoveError as exc:
            self.console.print(f"[red]{escape(str(exc))}[/red]")
            return view
        except (BrainUnavailableError, GameOverError) as exc:
            self.console.print(f"[red]{escape(str(exc))}[/red]")
            return view
        self.show_log_warning(new_view)
        self.show_turn(new_view)
        return new_view

    # -- debrief ------------------------------------------------------------

    def debrief(self, view: PlayerView) -> bool:
        """Show the debrief; return True to play again, False to quit."""
        self.console.print(Rule())
        self.console.print(render.steps("Debrief"))
        self.console.print(render.debrief(view))
        self.show_log_folder(view)
        while True:
            self.console.print(
                "1. Read the conversation again  2. Brain insights  3. Play again  "
                "4. Your games  5. Quit"
            )
            choice = self.term.ask("Choose", "3")
            if choice == "1":
                self.console.print(render.conversation(view))
            elif choice == "2":
                self.console.print(render.insights(view))
            elif choice == "3":
                return True
            elif choice == "4":
                self.your_games()
            elif choice in ("5", "q"):
                return False
            else:
                self.console.print("[red]Type a number from 1 to 5.[/red]")

    def your_games(self) -> None:
        views = self.session.games()
        if not views:
            self.console.print("[dim]No games yet in this run.[/dim]")
            return
        self.console.print(render.games_table(views))
        choice = self.term.ask("Open a game by number (Enter to go back)", "")
        if choice.isdigit() and 1 <= int(choice) <= len(views):
            view = views[int(choice) - 1]
            self.console.print(render.conversation(view))
            self.console.print(render.debrief(view) if view.ended else render.deal_panel(view))

