"""Keep .env.example complete and harmless."""

import re
from pathlib import Path

from investor_game.env_file import load_env_file

ROOT = Path(__file__).parents[1]
SOURCES = {
    ROOT / "src/investor_game/cli/app.py": r'envvar="([A-Z_]+)"',
    ROOT / "src/investor_game/config.py": r'get\("([A-Z_]+)"\)',
}


def variables_read_by_code() -> set[str]:
    names = set()
    for path, pattern in SOURCES.items():
        names |= set(re.findall(pattern, path.read_text(encoding="utf-8")))
    return names


def test_example_documents_every_variable():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#\s*([A-Z][A-Z0-9_]+)=", example, re.M))
    code = variables_read_by_code()
    assert len(code) >= 16
    assert code - documented == set(), "add these to .env.example"


def test_copying_example_changes_nothing():
    environ = {}
    result = load_env_file(ROOT / ".env.example", environ)
    assert result.loaded and result.bad_lines == ()
    assert environ == {}  # every assignment is commented out


def test_env_ignored_example_tracked():
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in rules
    assert not any(rule in (".env*", ".env.*", "*.example") for rule in rules)
