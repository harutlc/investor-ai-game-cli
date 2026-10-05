"""Games played during this run. Memory only: nothing is written to disk."""

from __future__ import annotations

from typing import Any

from .brain.investor import InvestorBrain
from .engine import Game
from .llmlog import LogRoot
from .models import Move, Pitch, PlayerView
from .personas import get_persona
from .voice.guarded import GuardedVoice


class Session:
    """The CLI's only entry point to games. Everything it returns is a ``PlayerView``."""

    def __init__(self, brain: InvestorBrain, voice: GuardedVoice,
                 log_root: LogRoot | None = None, backends: dict[str, Any] | None = None):
        self.brain = brain
        self.voice = voice
        self.log_root = log_root
        self.backends = backends or {}
        self._games: list[Game] = []

    def new_game(self, pitch: Pitch, persona_id: str) -> PlayerView:
        game_id = len(self._games) + 1
        game_log = None
        if self.log_root is not None:
            persona = get_persona(persona_id)
            game_log = self.log_root.start_game(game_id, persona_id, {
                "persona": {"id": persona_id, "name": persona.name},
                "pitch": pitch.model_dump(),
                **self.backends,
            })
        game = Game.start(game_id, pitch, persona_id, self.brain, self.voice, game_log)
        self._games.append(game)
        return game.view()

    def play(self, game_id: int, move: Move) -> PlayerView:
        return self._game(game_id).play(move)

    def games(self) -> list[PlayerView]:
        """Player views of every game in this run, newest first."""
        return [game.view() for game in reversed(self._games)]

    def get(self, game_id: int) -> PlayerView:
        return self._game(game_id).view()

    def _game(self, game_id: int) -> Game:
        return next(game for game in self._games if game.state.id == game_id)
