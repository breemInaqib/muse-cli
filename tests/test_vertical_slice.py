from __future__ import annotations

from typer.testing import CliRunner

from musecli.cli import app


def test_vertical_slice_output_shape_stays_stable(tmp_path) -> None:
    runner = CliRunner()

    add_result = runner.invoke(app, ["--data-dir", str(tmp_path), "add", "capture one thing"])
    assert add_result.exit_code == 0, add_result.output
    assert add_result.output == "added\n"

    inbox_result = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "inbox"],
        input="p",
    )
    assert inbox_result.exit_code == 0, inbox_result.output
    assert inbox_result.output == (
        "inbox\n\n"
        "  capture one thing\n\n"
        "  [k] keep   [d] discard   [p] pin   [q] quit\n"
    )

    focus = runner.invoke(app, ["--data-dir", str(tmp_path), "focus"], input="d")
    assert focus.exit_code == 0, focus.output
    assert focus.output == (
        "focus\n\n"
        "  capture one thing\n\n"
        "  [d] done   [q] quit\n"
    )

    check_in = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "4",
            "--note",
            "steady",
        ],
    )
    assert check_in.exit_code == 0, check_in.output
    assert check_in.output == "saved\n"

    populated_today = runner.invoke(app, ["--data-dir", str(tmp_path), "today"])
    assert populated_today.exit_code == 0, populated_today.output
    assert populated_today.output == "today\n\n  mood: 4\n  note: steady\n"
