"""Run the real console command in a subprocess, Setup to Debrief, offline."""

import os
import subprocess
import sys
from pathlib import Path


def test_offline_game_from_setup_to_debrief(tmp_path):
    script = Path(sys.executable).parent / "investor-game"
    stdin = "\n".join(["1", "", "", "", "", "", "y", "3", "5"]) + "\n"  # option 3 = accept
    env = {**os.environ, "COLUMNS": "120"}
    for name in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY", "INVESTOR_GAME_LOG_DIR"):
        env.pop(name, None)
    result = subprocess.run(
        [str(script), "--offline"], input=stdin, capture_output=True, text=True,
        timeout=60, env=env, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Deal closed" in result.stdout or "No deal" in result.stdout
    assert "Setup → Negotiation → Debrief" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []  # nothing written to disk


def test_log_dir_writes_only_inside_it(tmp_path):
    script = Path(sys.executable).parent / "investor-game"
    stdin = "\n".join(["2", "", "", "", "", "", "y", "3", "5"]) + "\n"
    env = {**os.environ, "COLUMNS": "120"}
    for name in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY", "INVESTOR_GAME_LOG_DIR"):
        env.pop(name, None)
    result = subprocess.run(
        [str(script), "--offline", "--log-dir", "logs"], input=stdin, capture_output=True,
        text=True, timeout=60, env=env, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert [p.name for p in tmp_path.iterdir()] == ["logs"]
    [game] = (tmp_path / "logs").iterdir()
    assert game.name.endswith("_g1_grace")
    assert "LLM logs: logs/" in result.stdout


def test_env_file_in_working_directory(tmp_path):
    script = Path(sys.executable).parent / "investor-game"
    (tmp_path / ".env").write_text(
        "# local settings\nINVESTOR_GAME_OFFLINE=true\nthis line is broken\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("INVESTOR_GAME_", "TYPESAFE_", "ANTHROPIC_", "LAYA_", "OLLAMA_"))}
    env["COLUMNS"] = "200"
    stdin = "\n".join(["1", "", "", "", "", "", "y", "3", "5"]) + "\n"
    result = subprocess.run([str(script)], input=stdin, capture_output=True, text=True,
                            timeout=60, env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "brain: stub · voice: stub" in result.stdout
    assert "settings: .env" in result.stdout
    assert "line(s) 3 could not be read" in result.stderr
    assert "this line is broken" not in result.stdout + result.stderr
