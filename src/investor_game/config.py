"""Settings from command-line flags and environment variables; backend construction."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .brain.investor import InvestorBrain
from .brain.stub import StubBrainBackend
from .brain.systemone import SystemOneBackend
from .voice.claude import ClaudeVoiceBackend
from .voice.guarded import GuardedVoice
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
    anthropic_api_key: str | None = None
    claude_model: str | None = None
    ollama_host: str | None = None
    ollama_model: str | None = None

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
            anthropic_api_key=get("ANTHROPIC_API_KEY"),
            claude_model=get("INVESTOR_GAME_CLAUDE_MODEL"),
            ollama_host=get("OLLAMA_HOST"),
            ollama_model=get("INVESTOR_GAME_OLLAMA_MODEL"),
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
        return f"brain: {self.brain} · voice: {self.voice}"


def build_brain(settings: Settings) -> InvestorBrain:
    if settings.brain == "jev":
        backend = SystemOneBackend.jev(
            settings.typesafe_api_key or "", settings.typesafe_base_url, settings.typesafe_model,
            timeout=settings.brain_timeout,
        )
    elif settings.brain == "laya":
        backend = SystemOneBackend.laya(
            settings.laya_base_url, settings.laya_model, timeout=settings.brain_timeout
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
