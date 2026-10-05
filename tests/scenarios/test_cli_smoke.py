"""Run the real console command in a subprocess, Setup to Debrief, offline."""

import os
import subprocess
import sys
from pathlib import Path


def test_offline_game_from_setup_to_debrief(tmp_path):
    script = Path(sys.executable).parent / "investor-game"
    stdin = "\n".join(["1", "", "", "", "", "", "y", "3", "5"]) + "\n"  # option 3 = accept
    env = {**os.environ, "COLUMNS": "120"}
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("TYPESAFE_API_KEY", None)
    result = subprocess.run(
        [str(script), "--offline"], input=stdin, capture_output=True, text=True,
        timeout=60, env=env, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Deal closed" in result.stdout or "No deal" in result.stdout
    assert "Setup → Negotiation → Debrief" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []  # nothing written to disk
