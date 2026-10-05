import io
import os
import sys

import pytest

from investor_game.cli import app as app_module

OUR_VARS = ("INVESTOR_GAME_", "TYPESAFE_", "LAYA_", "ANTHROPIC_", "OLLAMA_")


@pytest.fixture
def run_main(tmp_path, monkeypatch, capsys):
    """Run the real ``main()`` in ``tmp_path`` with an isolated os.environ."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(OUR_VARS)}
    monkeypatch.setattr(os, "environ", clean)
    monkeypatch.setattr(app_module, "_ENV_FILE", None)
    monkeypatch.chdir(tmp_path)

    def run(*args, dotenv=None, stdin="q\n", env=None):
        if dotenv is not None:
            (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
        os.environ.update(env or {})
        monkeypatch.setattr(sys, "argv", ["investor-game", *args])
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        with pytest.raises(SystemExit) as exit_info:
            app_module.main()
        out = capsys.readouterr()
        return exit_info.value.code, out.out, out.err

    return run


def test_keys_from_env_file(run_main):
    code, out, err = run_main(dotenv="INVESTOR_GAME_VOICE=claude\nANTHROPIC_API_KEY=sk-ant-123\n")
    assert code == 0, err
    assert "required" not in err
    assert "voice: claude" in out
    assert "settings: .env" in out
    assert "sk-ant-123" not in out + err


def test_real_environment_beats_env_file(run_main):
    code, out, _ = run_main(dotenv="INVESTOR_GAME_BRAIN=jev\nTYPESAFE_API_KEY=ts-1\n",
                            env={"INVESTOR_GAME_BRAIN": "stub"})
    assert code == 0
    assert "brain: stub" in out


def test_flag_beats_env_file(run_main):
    code, out, _ = run_main("--voice", "stub", dotenv="INVESTOR_GAME_VOICE=ollama\n")
    assert code == 0
    assert "voice: stub" in out


def test_no_env_file_no_message(run_main):
    code, out, err = run_main()
    assert code == 0
    assert ".env" not in out + err


def test_bad_line_warning_without_contents(run_main):
    code, out, err = run_main(dotenv="INVESTOR_GAME_OFFLINE=true\nnot valid sk-hidden\n")
    assert code == 0
    assert "line(s) 2 could not be read" in err
    assert "sk-hidden" not in out + err
    assert "brain: stub · voice: stub" in out


def test_env_file_enables_missing_key_error(run_main):
    code, _, err = run_main(dotenv="INVESTOR_GAME_VOICE=claude\n")
    assert code != 0
    assert "ANTHROPIC_API_KEY is required" in err
