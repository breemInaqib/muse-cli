from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import UUID

import pytest

from musecli.config import AppConfig
from musecli.session import (
    Activity,
    ActivityKind,
    ActivityStatus,
    Presentation,
    PresentationResult,
    SessionCommand,
    SessionController,
)


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig.defaults(tmp_path / "data")


def test_activity_contract_values_are_stable() -> None:
    assert [kind.value for kind in ActivityKind] == [
        "intent",
        "plan",
        "context",
        "permission",
        "tool",
        "verification",
        "result",
    ]
    assert [status.value for status in ActivityStatus] == [
        "pending",
        "active",
        "complete",
        "blocked",
        "failed",
        "skipped",
        "cancelled",
    ]


def test_activity_is_immutable_and_normalizes_details() -> None:
    activity = Activity(
        sequence=1,
        kind=ActivityKind.INTENT,
        status=ActivityStatus.COMPLETE,
        summary="Inspect the current work",
        display_details=["User-provided intent."],  # type: ignore[arg-type]
    )

    assert activity.display_details == ("User-provided intent.",)
    with pytest.raises(FrozenInstanceError):
        activity.summary = "changed"  # type: ignore[misc]


def test_activity_rejects_invalid_display_contract() -> None:
    with pytest.raises(ValueError, match="sequence must be positive"):
        Activity(
            sequence=0,
            kind=ActivityKind.INTENT,
            status=ActivityStatus.COMPLETE,
            summary="Intent",
        )
    with pytest.raises(ValueError, match="summary must not be empty"):
        Activity(
            sequence=1,
            kind=ActivityKind.INTENT,
            status=ActivityStatus.COMPLETE,
            summary=" ",
        )


def test_submit_records_exact_honest_demonstration(tmp_path: Path) -> None:
    controller = SessionController(_config(tmp_path), session_id="session-test")

    activities = controller.submit("  Improve the local workflow  ")

    assert [activity.sequence for activity in activities] == list(range(1, 8))
    assert [activity.kind for activity in activities] == list(ActivityKind)
    assert [activity.status for activity in activities] == [
        ActivityStatus.COMPLETE,
        ActivityStatus.COMPLETE,
        ActivityStatus.SKIPPED,
        ActivityStatus.SKIPPED,
        ActivityStatus.SKIPPED,
        ActivityStatus.SKIPPED,
        ActivityStatus.COMPLETE,
    ]
    assert [activity.summary for activity in activities] == [
        "Improve the local workflow",
        "Record the intent.",
        "No context was gathered.",
        "No permission was requested or granted.",
        "No tool, shell, network, or mutation ran.",
        "There was no generated change to verify.",
        "Demonstration completed; the requested task was not executed.",
    ]
    assert activities[-1].display_details == (
        "No model, tools, permissions, network, or files were used.",
    )
    assert controller.state.current_plan == (
        "Record the intent.",
        "Expose it through both presentations.",
        "Finish without external execution.",
    )
    assert tuple(controller.state.activities) == activities


def test_multiple_submissions_keep_one_session_and_monotonic_sequence(
    tmp_path: Path,
) -> None:
    controller = SessionController(_config(tmp_path), session_id="stable-session")

    first = controller.submit("First intent")
    second = controller.submit("Second intent")

    assert controller.state.session_id == "stable-session"
    assert first[-1].sequence == 7
    assert second[0].sequence == 8
    assert second[-1].sequence == 14
    assert [activity.summary for activity in controller.activities_for(ActivityKind.INTENT)] == [
        "First intent",
        "Second intent",
    ]
    assert controller.latest_result() is second[-1]


def test_empty_and_rejected_submissions_do_not_mutate_state(tmp_path: Path) -> None:
    config = _config(tmp_path)
    controller = SessionController(config, session_id="session-test")

    assert controller.submit("   ") == ()
    with pytest.raises(ValueError, match="shell execution is unavailable"):
        controller.submit("  ! touch private.txt")

    assert controller.state.activities == []
    assert controller.state.current_plan == ()
    assert controller.latest_result() is None
    assert not config.data_dir.exists()


def test_submit_sanitizes_intent_for_direct_terminal_rendering(tmp_path: Path) -> None:
    controller = SessionController(_config(tmp_path), session_id="session-test")

    activities = controller.submit("  Inspect\n\t\x1b[31mthe\u202e workflow  ")

    intent = activities[0].summary
    assert intent == "Inspect [31mthe workflow"
    assert "\n" not in intent
    assert "\x1b" not in intent
    assert "\u202e" not in intent
    assert all(character.isprintable() for character in intent)


def test_controls_cannot_hide_shell_syntax(tmp_path: Path) -> None:
    controller = SessionController(_config(tmp_path), session_id="session-test")

    with pytest.raises(ValueError, match="shell execution is unavailable"):
        controller.submit("\x00! touch private.txt")

    assert controller.state.activities == []


def test_generated_session_id_is_stable_and_writes_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    controller = SessionController(config)

    UUID(controller.state.session_id)
    original_id = controller.state.session_id
    controller.submit("Show the session")

    assert controller.state.session_id == original_id
    assert not config.data_dir.exists()


def test_session_id_must_not_be_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="session id must not be empty"):
        SessionController(_config(tmp_path), session_id="  ")


def test_presentation_result_defaults_to_success() -> None:
    result = PresentationResult(Presentation.WORKSPACE)

    assert result.presentation is Presentation.WORKSPACE
    assert result.exit_code == 0
    assert [presentation.value for presentation in Presentation] == [
        "simple",
        "workspace",
        "exit",
    ]


def test_command_dispatch_is_shared_case_insensitive_and_display_safe(tmp_path: Path) -> None:
    controller = SessionController(_config(tmp_path), session_id="session-test")

    assert controller.dispatch_command("/HELP").command is SessionCommand.HELP
    assert controller.dispatch_command("/workspace").command is SessionCommand.WORKSPACE
    assert controller.dispatch_command("/plan extra").error == (
        "error: command does not accept arguments: /plan"
    )
    assert controller.dispatch_command("/unsafe\x1b[31m").error == (
        "error: command does not accept arguments: /unsafe"
    )
    assert controller.dispatch_command("/unknown").error == "error: unknown command /unknown"


def test_capability_boundaries_are_explicit_and_stable(tmp_path: Path) -> None:
    controller = SessionController(_config(tmp_path), session_id="session-test")

    assert controller.capability_boundaries() == (
        "model execution: off",
        "context retrieval: off",
        "tool and shell execution: off",
        "network access: off",
        "file mutation: off",
    )
