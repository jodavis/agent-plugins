"""Tests for run_validation.py — run_commands() runs each configured validation command in
order from the repo root, stopping at the first failure, and main() wires the merged project
configuration's `validation` list into run_commands().

Covers:
- All commands succeed → exit 0, every command run in order from the repo root.
- First command fails → later commands are not run; the failing command's exit code is returned.
- Empty/missing `validation` list → exit 0 without running anything.
- main(): reads `validation` from merged config and passes it plus repo_root through to
  run_commands(); a config-load error is reported and returns 1 without running anything.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from run_validation import main, run_commands


def expect_run_returns(run_mock: MagicMock, returncode: int) -> None:
    run_mock.return_value = MagicMock(spec=subprocess.CompletedProcess, returncode=returncode)


class TestRunCommandsAllSucceed:
    def test_run_commands_all_commands_succeed_returns_zero(self, tmp_path):
        # Arrange
        run_mock = MagicMock(spec=subprocess.run)
        expect_run_returns(run_mock, 0)
        commands = ["echo one", "echo two", "echo three"]

        # Act
        result = run_commands(commands, tmp_path, run=run_mock)

        # Assert
        assert result == 0
        assert run_mock.call_count == 3

    def test_run_commands_runs_each_command_in_order_from_repo_root(self, tmp_path):
        # Arrange
        run_mock = MagicMock(spec=subprocess.run)
        expect_run_returns(run_mock, 0)
        commands = ["make build", "make test"]

        # Act
        run_commands(commands, tmp_path, run=run_mock)

        # Assert
        calls = run_mock.call_args_list
        assert [call.args[0] for call in calls] == commands
        assert all(call.kwargs["cwd"] == tmp_path for call in calls)
        assert all(call.kwargs["shell"] is True for call in calls)
        assert all(call.kwargs["timeout"] for call in calls)


class TestRunCommandsFirstCommandFails:
    def test_run_commands_first_command_fails_short_circuits_and_returns_its_exit_code(self, tmp_path):
        # Arrange
        run_mock = MagicMock(spec=subprocess.run)
        run_mock.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=1),
            MagicMock(spec=subprocess.CompletedProcess, returncode=0),
        ]
        commands = ["make build", "make test"]

        # Act
        result = run_commands(commands, tmp_path, run=run_mock)

        # Assert
        assert result == 1
        assert run_mock.call_count == 1

    def test_run_commands_second_command_fails_stops_before_third(self, tmp_path):
        # Arrange
        run_mock = MagicMock(spec=subprocess.run)
        run_mock.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0),
            MagicMock(spec=subprocess.CompletedProcess, returncode=2),
            MagicMock(spec=subprocess.CompletedProcess, returncode=0),
        ]
        commands = ["make build", "make test", "make package"]

        # Act
        result = run_commands(commands, tmp_path, run=run_mock)

        # Assert
        assert result == 2
        assert run_mock.call_count == 2


class TestRunCommandsEmptyOrMissing:
    @pytest.mark.parametrize(
        "commands",
        [
            pytest.param(None, id="missing"),
            pytest.param([], id="empty_list"),
        ],
    )
    def test_run_commands_empty_or_missing_returns_zero_without_running_anything(self, tmp_path, commands):
        # Arrange
        run_mock = MagicMock(spec=subprocess.run)

        # Act
        result = run_commands(commands, tmp_path, run=run_mock)

        # Assert
        assert result == 0
        run_mock.assert_not_called()


class TestMainWiresConfigIntoRunCommands:
    def test_main_passes_configured_validation_list_and_repo_root_to_run_commands(self, tmp_path):
        # Arrange
        config = {"validation": ["make build", "make test"]}
        with patch("run_validation.build_merged_config", return_value=config), \
             patch("run_validation.run_commands", return_value=0) as run_commands_mock:
            # Act
            result = main(["--repo-root", str(tmp_path)])

        # Assert
        assert result == 0
        run_commands_mock.assert_called_once_with(["make build", "make test"], tmp_path)

    def test_main_no_validation_configured_returns_zero(self, tmp_path):
        # Arrange
        config = {}
        with patch("run_validation.build_merged_config", return_value=config), \
             patch("run_validation.run_commands", return_value=0) as run_commands_mock:
            # Act
            result = main(["--repo-root", str(tmp_path)])

        # Assert
        assert result == 0
        run_commands_mock.assert_called_once_with(None, tmp_path)

    def test_main_config_load_error_prints_error_and_returns_one(self, tmp_path, capsys):
        # Arrange
        with patch("run_validation.build_merged_config", side_effect=RuntimeError("boom")):
            # Act
            result = main(["--repo-root", str(tmp_path)])

        # Assert
        assert result == 1
        captured = capsys.readouterr()
        assert "boom" in captured.err

    def test_main_missing_repo_root_argument_exits_nonzero(self):
        # Act & Assert
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0


class TestMainCliInvocation:
    SCRIPTS_DIR = Path(__file__).parent

    def test_main_cli_no_commands_configured_exits_zero(self, tmp_path, monkeypatch):
        # Arrange — an isolated HOME with no machine-level config, and a repo with no
        # .dev-team/config.yaml, both fall back to the shipped default, which ships with
        # no validation commands configured.
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir()
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Act
        result = subprocess.run(
            [sys.executable, str(self.SCRIPTS_DIR / "run_validation.py"), "--repo-root", str(repo_root)],
            capture_output=True, text=True, timeout=30,
        )

        # Assert
        assert result.returncode == 0, f"stderr: {result.stderr}"
