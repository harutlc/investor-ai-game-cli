import logging

from investor_game.env_file import load_env_file

VALID = """\
# backends
export INVESTOR_GAME_VOICE=claude
ANTHROPIC_API_KEY="sk-ant-123"
OLLAMA_HOST='http://gpu-box:11434'

INVESTOR_GAME_BRAIN=jev  # inline comment
"""


def write(tmp_path, text, name=".env"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_values_applied(tmp_path):
    environ = {}
    result = load_env_file(write(tmp_path, VALID), environ)
    assert result.loaded
    assert environ == {
        "INVESTOR_GAME_VOICE": "claude",
        "ANTHROPIC_API_KEY": "sk-ant-123",
        "OLLAMA_HOST": "http://gpu-box:11434",
        "INVESTOR_GAME_BRAIN": "jev",
    }
    assert set(result.applied) == set(environ)
    assert result.bad_lines == () and result.warning is None


def test_real_environment_wins(tmp_path):
    environ = {"INVESTOR_GAME_BRAIN": "stub"}
    result = load_env_file(write(tmp_path, VALID), environ)
    assert environ["INVESTOR_GAME_BRAIN"] == "stub"
    assert "INVESTOR_GAME_BRAIN" not in result.applied


def test_bad_line_reported_by_number_only(tmp_path, caplog, capsys):
    text = "A=1\nB=2\nthis is not valid sk-hidden\nC=3\n"
    environ = {}
    with caplog.at_level(logging.DEBUG):
        result = load_env_file(write(tmp_path, text), environ)
    assert environ == {"A": "1", "B": "2", "C": "3"}
    assert result.bad_lines == (3,)
    assert result.warning == "Warning: .env line(s) 3 could not be read and were skipped."
    assert "sk-hidden" not in (result.warning or "")
    captured = capsys.readouterr()
    assert "could not parse" not in captured.err + caplog.text  # dotenv's own warning muted
    assert not logging.getLogger("dotenv.main").disabled  # restored afterwards


def test_missing_file_is_silent(tmp_path):
    result = load_env_file(tmp_path / ".env", {})
    assert not result.loaded and result.warning is None


def test_directory_named_env_is_ignored(tmp_path):
    (tmp_path / ".env").mkdir()
    result = load_env_file(tmp_path / ".env", {})
    assert not result.loaded and result.warning is None


def test_unreadable_file_warns(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(b"A=\xff\xfe\n")
    environ = {}
    result = load_env_file(path, environ)
    assert not result.loaded
    assert environ == {}
    assert result.warning == "Warning: .env could not be read and was ignored."


def test_result_holds_no_values(tmp_path):
    result = load_env_file(write(tmp_path, VALID), {})
    assert "sk-ant-123" not in repr(result)


def test_bare_name_without_value_is_skipped(tmp_path):
    environ = {}
    load_env_file(write(tmp_path, "JUST_A_NAME\nA=1\n"), environ)
    assert environ == {"A": "1"}
