"""Games played during this run. Memory only: nothing is written to disk."""

from __future__ import annotations

from .brain.investor import InvestorBrain
from .engine import Game
from .models import Move, Pitch, PlayerView
from .voice.guarded import GuardedVoice


class Session:
    """The CLI's only entry point to games. Everything it returns is a ``PlayerView``."""

    def __init__(self, brain: InvestorBrain, voice: GuardedVoice):
        self.brain = brain
        self.voice = voice
        self._games: list[Game] = []

    def new_game(self, pitch: Pitch, persona_id: str) -> PlayerView:
        game = Game.start(len(self._games) + 1, pitch, persona_id, self.brain, self.voice)
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
