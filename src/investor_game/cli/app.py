"""``investor-game`` console command."""

from __future__ import annotations

import logging
import sys
from typing import Annotated

import typer
from rich.console import Console

from .. import __version__
from ..config import ConfigError, Settings, build_brain, build_voice
from ..session import Session
from .screens import App, Terminal

EXIT_INTERRUPTED = 130

app = typer.Typer(add_completion=False, help="Negotiate a startup investment against an AI "
                  "investor in your terminal. Games live in memory only: quitting discards them.")


def _version(value: bool) -> None:
    if value:
        typer.echo(f"investor-game {__version__}")
        raise typer.Exit()


@app.command()
def play(
    brain: Annotated[str | None, typer.Option(
        "--brain", envvar="INVESTOR_GAME_BRAIN",
        help="Decision AI: jev (TypeSafe), laya (local) or stub.")] = None,
    voice: Annotated[str | None, typer.Option(
        "--voice", envvar="INVESTOR_GAME_VOICE",
        help="Text AI: claude (Anthropic), ollama (local) or stub.")] = None,
    offline: Annotated[bool, typer.Option(
        "--offline", envvar="INVESTOR_GAME_OFFLINE",
        help="Use the built-in stub brain and voice (no network).")] = False,
    brain_timeout: Annotated[float, typer.Option(
        "--brain-timeout", envvar="INVESTOR_GAME_BRAIN_TIMEOUT",
        help="Seconds to wait for a brain decision.")] = 10.0,
    voice_timeout: Annotated[float, typer.Option(
        "--voice-timeout", envvar="INVESTOR_GAME_VOICE_TIMEOUT",
        help="Seconds to wait for a voice reply.")] = 60.0,
    debug: Annotated[bool, typer.Option(
        "--debug", envvar="INVESTOR_GAME_DEBUG",
        help="Print detailed errors to stderr.")] = False,
    version: Annotated[bool, typer.Option(
        "--version", callback=_version, is_eager=True, help="Show the version and exit.")] = False,
) -> None:
    """Play the Investor Negotiation Game.

    Games live in memory only: quitting the program discards them.
    """
    console = Console()
    errors = Console(stderr=True)
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.CRITICAL,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        settings = Settings.build(brain, voice, offline, brain_timeout, voice_timeout, debug)
    except ConfigError as exc:
        errors.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from None
    missing = settings.missing()
    if missing:
        for problem in missing:
            errors.print(f"[red]{problem}[/red]")
        errors.print("Set it in your environment, or run with --offline to play without AI.")
        raise typer.Exit(2)

    session = Session(build_brain(settings), build_voice(settings))
    try:
        App(Terminal(console), session, settings.describe()).run()
    except KeyboardInterrupt:
        console.print("\nGoodbye! 👋")
        raise typer.Exit(EXIT_INTERRUPTED) from None
    except EOFError:
        console.print("\nGoodbye! 👋")
        raise typer.Exit(0) from None
    except Exception:
        if debug:
            errors.print_exception()
        else:
            errors.print("[red]Something went wrong. Run with --debug for details.[/red]")
        raise typer.Exit(1) from None
    console.print("Goodbye! 👋")


def main() -> None:
    app()
