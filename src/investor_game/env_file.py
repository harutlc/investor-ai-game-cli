"""Load a ``.env`` file into the environment without overriding real variables."""

from __future__ import annotations

import io
import logging
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from dotenv.parser import parse_stream

DOTENV_LOGGER = "dotenv.main"


@dataclass(frozen=True)
class EnvFileResult:
    """What happened when loading; holds variable names only, never values."""

    path: Path
    loaded: bool
    applied: tuple[str, ...] = ()
    bad_lines: tuple[int, ...] = ()
    warning: str | None = None


def load_env_file(path: Path, environ: MutableMapping[str, str]) -> EnvFileResult:
    """Apply ``NAME=value`` entries from ``path`` to ``environ`` where not already set.

    A missing file is silently ignored. Unparseable lines are skipped and reported by
    line number only (their text may contain secrets). Never raises.
    """
    if not path.is_file():
        return EnvFileResult(path, loaded=False)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return EnvFileResult(path, loaded=False,
                             warning=f"Warning: {path.name} could not be read and was ignored.")

    logger = logging.getLogger(DOTENV_LOGGER)
    was_disabled = logger.disabled
    logger.disabled = True  # we report bad lines ourselves, once
    try:
        bad_lines = tuple(
            binding.original.line for binding in parse_stream(io.StringIO(text)) if binding.error
        )
        values = dotenv_values(stream=io.StringIO(text))
    finally:
        logger.disabled = was_disabled

    applied = []
    for name, value in values.items():
        if value is None or name in environ:
            continue  # real environment wins; bare names without "=" carry no value
        environ[name] = value
        applied.append(name)

    warning = None
    if bad_lines:
        lines = ", ".join(str(line) for line in bad_lines)
        warning = f"Warning: {path.name} line(s) {lines} could not be read and were skipped."
    return EnvFileResult(path, loaded=True, applied=tuple(applied), bad_lines=bad_lines,
                         warning=warning)
