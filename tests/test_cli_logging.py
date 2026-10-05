import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from investor_game.brain.investor import InvestorBrain
from investor_game.brain.stub import StubBrainBackend
from investor_game.cli import app as app_module
from investor_game.cli.screens import App, ScriptedTerminal
from investor_game.config import ConfigError, Settings, build_log_root
from investor_game.llmlog import LogRoot
from investor_game.session import Session
from investor_game.voice.guarded import GuardedVoice
from investor_game.voice.stub import StubVoiceBackend

DEFAULTS = ["", "", "", "", ""]
runner = CliRunner()


# --- configuration ----------------------------------------------------------


def test_log_dir_off_by_default():
    settings = Settings.build(env={})
    assert settings.log_dir is None
    assert build_log_root(settings) is None
    assert "logs:" not in settings.describe()


def test_log_dir_from_env_and_flag():
    assert Settings.build(env={"INVESTOR_GAME_LOG_DIR": "./logs"}).log_dir == Path("logs")
    settings = Settings.build(env={"INVESTOR_GAME_LOG_DIR": "./logs"}, log_dir="other")
    assert settings.log_dir == Path("other")
    assert "logs: other" in settings.describe()


def test_log_root_gets_secrets():
    settings = Settings.build("jev", "claude", log_dir="logs",
                              env={"TYPESAFE_API_KEY": "ts-1234", "ANTHROPIC_API_KEY": "sk-5678"})
    root = build_log_root(settings)
    assert root.secrets == ["ts-1234", "sk-5678"]
    assert settings.backends() == {
        "brain": {"backend": "jev", "model": "jev-latest"},
        "voice": {"backend": "claude", "model": "claude-opus-5-5"},
    }


def test_log_dir_that_is_a_file(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("x")
    with pytest.raises(ConfigError, match="must be a folder"):
        Settings.build(env={}, log_dir=notes)
    result = runner.invoke(app_module.app, ["--offline", "--log-dir", str(notes)])
    assert result.exit_code != 0
    assert "must be a folder" in result.output
    assert "Setup" not in result.output


def test_env_var_enables_logging_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("INVESTOR_GAME_LOG_DIR", str(tmp_path / "logs"))
    result = runner.invoke(app_module.app, ["--offline"],
                           input="\n".join(["1", *DEFAULTS, "y", "3", "5"]) + "\n")
    assert result.exit_code == 0, result.output
    [folder] = (tmp_path / "logs").iterdir()
    assert folder.name.endswith("_g1_rex")
    assert [p.name for p in folder.iterdir()] == ["game.json"]  # stubs are not logged


# --- screens ----------------------------------------------------------------


def run_app(answers, log_root=None):
    session = Session(InvestorBrain(StubBrainBackend()), GuardedVoice(StubVoiceBackend()),
                      log_root=log_root)
    banner = "brain: stub · voice: stub" + (f" · logs: {log_root.path}" if log_root else "")
    term = ScriptedTerminal(answers)
    try:
        App(term, session, banner).run()
    except EOFError:
        pass
    return term.console.export_text(), session


def test_log_folder_shown_when_on(tmp_path):
    root = LogRoot(tmp_path / "logs")
    output, session = run_app(["1", *DEFAULTS, "y", "3", "5"], root)
    folder = session.games()[0].log_folder
    assert f"logs: {root.path}" in output
    assert output.count(f"LLM logs: {folder}") == 2  # negotiation start and debrief


def test_no_log_lines_when_off():
    output, _ = run_app(["1", *DEFAULTS, "y", "3", "5"])
    assert "LLM logs" not in output
    assert "logs:" not in output


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_log_warning_shown_once(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        output, session = run_app(
            ["4", *DEFAULTS, "y", "o", "500k", "15", "y", "m", "Please, more?", "q", "y", "5"],
            LogRoot(locked / "logs"))
    finally:
        locked.chmod(0o700)
    assert session.games()[0].turn >= 2  # the game went on normally
    assert output.count("LLM logging stopped for this game") == 1
