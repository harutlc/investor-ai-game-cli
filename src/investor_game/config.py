"""Settings from command-line flags and environment variables; backend construction."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .brain.investor import InvestorBrain
from .brain.stub import StubBrainBackend
from .brain.systemone import AUTO_MODEL_LABEL, JEV_MODEL, LAYA_MODEL, SystemOneBackend
from .llmlog import LogRoot
from .voice.claude import DEFAULT_MODEL as CLAUDE_MODEL
from .voice.claude import ClaudeVoiceBackend
from .voice.guarded import GuardedVoice
from .voice.ollama import DEFAULT_MODEL as OLLAMA_MODEL
from .voice.ollama import OllamaVoiceBackend
from .voice.stub import StubVoiceBackend

BRAINS = ("jev", "laya", "stub")
VOICES = ("claude", "ollama", "stub")


class ConfigError(ValueError):
    """Settings are missing or invalid; the message is safe to show."""


@dataclass(frozen=True)
class Settings:
    brain: str
    voice: str
    brain_timeout: float = 10.0
    voice_timeout: float = 60.0
    debug: bool = False
    typesafe_api_key: str | None = None
    typesafe_base_url: str | None = None
    typesafe_model: str | None = None
    laya_base_url: str | None = None
    laya_model: str | None = None
    laya_api_key: str | None = None
    anthropic_api_key: str | None = None
    claude_model: str | None = None
    ollama_host: str | None = None
    ollama_model: str | None = None
    log_dir: Path | None = None

    @classmethod
    def build(
        cls,
        brain: str | None = None,
        voice: str | None = None,
        offline: bool = False,
        brain_timeout: float = 10.0,
        voice_timeout: float = 60.0,
        debug: bool = False,
        env: Mapping[str, str] | None = None,
        log_dir: str | Path | None = None,
    ) -> Settings:
        """Flags win; otherwise use a real backend only when its key is set, else the stub."""
        env = os.environ if env is None else env

        def get(name: str) -> str | None:
            value = env.get(name, "").strip()
            return value or None

        if offline:
            brain, voice = "stub", "stub"
        brain = (brain or ("jev" if get("TYPESAFE_API_KEY") else "stub")).lower()
        voice = (voice or ("claude" if get("ANTHROPIC_API_KEY") else "stub")).lower()
        if brain not in BRAINS:
            raise ConfigError(f"Unknown brain {brain!r}. Choose one of: {', '.join(BRAINS)}.")
        if voice not in VOICES:
            raise ConfigError(f"Unknown voice {voice!r}. Choose one of: {', '.join(VOICES)}.")
        if brain_timeout <= 0 or voice_timeout <= 0:
            raise ConfigError("Timeouts must be more than 0 seconds.")
        log_path = Path(log_dir) if log_dir else (
            Path(get("INVESTOR_GAME_LOG_DIR")) if get("INVESTOR_GAME_LOG_DIR") else None)
        if log_path is not None and log_path.exists() and not log_path.is_dir():
            raise ConfigError(f"The log directory must be a folder: {log_path}")
        return cls(
            brain=brain,
            voice=voice,
            brain_timeout=brain_timeout,
            voice_timeout=voice_timeout,
            debug=debug,
            typesafe_api_key=get("TYPESAFE_API_KEY"),
            typesafe_base_url=get("TYPESAFE_BASE_URL"),
            typesafe_model=get("TYPESAFE_MODEL"),
            laya_base_url=get("LAYA_BASE_URL"),
            laya_model=get("LAYA_MODEL"),
            laya_api_key=get("LAYA_API_KEY"),
            anthropic_api_key=get("ANTHROPIC_API_KEY"),
            claude_model=get("INVESTOR_GAME_CLAUDE_MODEL"),
            ollama_host=get("OLLAMA_HOST"),
            ollama_model=get("INVESTOR_GAME_OLLAMA_MODEL"),
            log_dir=log_path,
        )

    def missing(self) -> list[str]:
        """Plain messages for every required setting the chosen backends lack."""
        problems = []
        if self.brain == "jev" and not self.typesafe_api_key:
            problems.append("TYPESAFE_API_KEY is required for the jev brain.")
        if self.voice == "claude" and not self.anthropic_api_key:
            problems.append("ANTHROPIC_API_KEY is required for the claude voice.")
        return problems

    def describe(self) -> str:
        text = f"brain: {self.brain} · voice: {self.voice}"
        return f"{text} · logs: {self.log_dir}" if self.log_dir else text

    def secrets(self) -> list[str]:
        keys = (self.typesafe_api_key, self.anthropic_api_key, self.laya_api_key)
        return [s for s in keys if s]

    def backends(self) -> dict[str, dict[str, str | None]]:
        """Backend and model names for each game's ``game.json``."""
        brain_models = {"jev": self.typesafe_model or JEV_MODEL,
                        "laya": self.laya_model or LAYA_MODEL or AUTO_MODEL_LABEL}
        voice_models = {"claude": self.claude_model or CLAUDE_MODEL,
                        "ollama": self.ollama_model or OLLAMA_MODEL}
        return {
            "brain": {"backend": self.brain, "model": brain_models.get(self.brain)},
            "voice": {"backend": self.voice, "model": voice_models.get(self.voice)},
        }


def build_log_root(settings: Settings) -> LogRoot | None:
    if settings.log_dir is None:
        return None
    return LogRoot(settings.log_dir, secrets=settings.secrets())


def build_brain(settings: Settings) -> InvestorBrain:
    if settings.brain == "jev":
        backend = SystemOneBackend.jev(
            settings.typesafe_api_key or "", settings.typesafe_base_url, settings.typesafe_model,
            timeout=settings.brain_timeout,
        )
    elif settings.brain == "laya":
        backend = SystemOneBackend.laya(
            settings.laya_base_url, settings.laya_model, api_key=settings.laya_api_key,
            timeout=settings.brain_timeout,
        )
    else:
        backend = StubBrainBackend()
    return InvestorBrain(backend)


def build_voice(settings: Settings) -> GuardedVoice:
    if settings.voice == "claude":
        backend = ClaudeVoiceBackend(settings.anthropic_api_key, settings.claude_model,
                                     timeout=settings.voice_timeout)
    elif settings.voice == "ollama":
        backend = OllamaVoiceBackend(settings.ollama_host, settings.ollama_model,
                                     timeout=settings.voice_timeout)
    else:
        backend = StubVoiceBackend()
    return GuardedVoice(backend)
