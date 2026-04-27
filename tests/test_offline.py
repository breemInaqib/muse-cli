from __future__ import annotations

import socket
from pathlib import Path

from typer.testing import CliRunner

from musecli.cli import app


class _NoNetworkSocket(socket.socket):
    def connect(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("network disabled for test")

def test_cli_commands_do_not_require_network(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(socket, "socket", _NoNetworkSocket)

    added = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "add",
            "offline check",
        ],
    )
    assert added.exit_code == 0, added.output
    assert added.output == "added\n"

    inbox = runner.invoke(app, ["--data-dir", str(tmp_path), "inbox"])
    assert inbox.exit_code == 0, inbox.output
    assert "offline check" in inbox.output
