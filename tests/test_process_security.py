import subprocess
from pathlib import Path

import pytest

from chinese2lean.verification.process import (
    AllowedCommand,
    ControlledProcessRunner,
    ProcessPolicyError,
)


def test_controlled_runner_uses_an_exact_allowlisted_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / 'tool.exe'
    executable.write_bytes(b'')
    observed: dict[str, object] = {}

    def complete(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed['command'] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0, 'ok', '')

    monkeypatch.setattr(subprocess, 'run', complete)
    runner = ControlledProcessRunner(
        {
            'health': AllowedCommand(
                executable=executable,
                fixed_arguments=('check',),
                working_directory=tmp_path,
                timeout_seconds=15,
            )
        }
    )

    result = runner.execute('health')

    assert result.success
    assert observed['command'] == [str(executable.resolve()), 'check']
    assert observed['cwd'] == tmp_path.resolve()
    assert observed['timeout'] == 15
    assert observed['shell'] is False


def test_controlled_runner_rejects_unknown_actions_arguments_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / 'tool.exe'
    executable.write_bytes(b'')
    called = False

    def unexpected(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(subprocess, 'run', unexpected)
    runner = ControlledProcessRunner(
        {
            'health': AllowedCommand(
                executable=executable,
                working_directory=tmp_path,
                timeout_seconds=15,
            )
        }
    )

    with pytest.raises(ProcessPolicyError, match='未列入白名单'):
        runner.execute('unknown')
    with pytest.raises(ProcessPolicyError, match='参数'):
        runner.execute('health', arguments=('user-input',))
    with pytest.raises(ProcessPolicyError, match='工作目录'):
        runner.execute('health', cwd=tmp_path.parent)
    assert not called


def test_controlled_runner_returns_a_structured_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / 'tool.exe'
    executable.write_bytes(b'')

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=['tool.exe'], timeout=5, output='partial')

    monkeypatch.setattr(subprocess, 'run', timeout)
    runner = ControlledProcessRunner(
        {
            'health': AllowedCommand(
                executable=executable,
                working_directory=tmp_path,
                timeout_seconds=5,
            )
        }
    )

    result = runner.execute('health')

    assert not result.success
    assert result.timed_out
    assert result.error_code == 'PROCESS_TIMEOUT'
    assert result.stdout == 'partial'
