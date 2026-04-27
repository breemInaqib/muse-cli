from __future__ import annotations

import subprocess

import pytest

from musecli.utils import ClipboardUnavailableError, read_clipboard_text


def test_read_clipboard_prefers_first_available_provider(monkeypatch) -> None:
    monkeypatch.setattr("musecli.utils.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "musecli.utils.shutil.which",
        lambda name: "/usr/bin/xclip" if name == "xclip" else None,
    )

    calls: list[list[str]] = []

    def fake_run(command, check, capture_output, text):  # type: ignore[no-untyped-def]
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="copied text\n")

    monkeypatch.setattr("musecli.utils.subprocess.run", fake_run)

    assert read_clipboard_text() == "copied text\n"
    assert calls == [["xclip", "-selection", "clipboard", "-o"]]


def test_read_clipboard_raises_when_no_provider_exists(monkeypatch) -> None:
    monkeypatch.setattr("musecli.utils.platform.system", lambda: "Linux")
    monkeypatch.setattr("musecli.utils.shutil.which", lambda name: None)

    with pytest.raises(ClipboardUnavailableError):
        read_clipboard_text()
