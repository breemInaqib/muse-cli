from __future__ import annotations

import sys
from pathlib import Path

import typer
from typer.testing import CliRunner

from musecli import cli
from musecli.cli import app


def test_tty_bare_muse_starts_simple_session_with_home_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(config, *, initial_workspace, home_lines=()) -> None:
        captured["config"] = config
        captured["initial_workspace"] = initial_workspace
        captured["home_lines"] = list(home_lines)
        raise typer.Exit()

    monkeypatch.setattr(cli, "_is_interactive_terminal", lambda: True)
    monkeypatch.setattr(cli, "_run_interactive", fake_run)

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert captured["initial_workspace"] is False
    assert captured["home_lines"] == [
        "museCLI",
        "",
        "  inbox: 0",
        "",
        "focus",
        "  empty",
        "",
        "today",
        "  no check-in",
    ]
    assert (tmp_path / "config.json").exists()


def test_tui_starts_workspace_without_loading_home(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_home(_config):
        raise AssertionError("workspace startup must not load the home view")

    def fake_run(config, *, initial_workspace, home_lines=()) -> None:
        captured["config"] = config
        captured["initial_workspace"] = initial_workspace
        captured["home_lines"] = list(home_lines)
        raise typer.Exit()

    monkeypatch.setattr(cli, "_is_interactive_terminal", lambda: True)
    monkeypatch.setattr(cli, "_home_lines", fake_home)
    monkeypatch.setattr(cli, "_run_interactive", fake_run)

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), "--tui"])

    assert result.exit_code == 0, result.output
    assert captured["initial_workspace"] is True
    assert captured["home_lines"] == []


def test_tui_requires_an_interactive_terminal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_interactive_terminal", lambda: False)

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), "--tui"])

    assert result.exit_code == 1
    assert result.output == "error: --tui requires an interactive terminal\n"
    assert not (tmp_path / "config.json").exists()
    assert not (tmp_path / "muse.db").exists()


def test_tui_cannot_be_combined_with_a_command(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["--data-dir", str(tmp_path), "--tui", "today"],
    )

    assert result.exit_code == 1
    assert result.output == "error: --tui cannot be used with a command\n"
    assert not (tmp_path / "config.json").exists()
    assert not (tmp_path / "muse.db").exists()


def test_help_does_not_import_tui(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "musecli.tui", raising=False)

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "musecli.tui" not in sys.modules
