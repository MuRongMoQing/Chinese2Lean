from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field


class ProcessPolicyError(ValueError):
    pass


def _reject_arguments(arguments: tuple[str, ...]) -> bool:
    return not arguments


ArgumentPolicy = Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True)
class AllowedCommand:
    executable: Path
    working_directory: Path
    timeout_seconds: float
    fixed_arguments: tuple[str, ...] = ()
    argument_policy: ArgumentPolicy = _reject_arguments

    def __post_init__(self) -> None:
        executable = self.executable.resolve()
        working_directory = self.working_directory.resolve()
        if not executable.is_file():
            raise ProcessPolicyError(f'白名单可执行文件不存在：{executable}')
        if not working_directory.is_dir():
            raise ProcessPolicyError(f'白名单工作目录不存在：{working_directory}')
        if not 0 < self.timeout_seconds <= 600:
            raise ProcessPolicyError('subprocess timeout 必须在 0 到 600 秒之间')
        object.__setattr__(self, 'executable', executable)
        object.__setattr__(self, 'working_directory', working_directory)


class ControlledProcessResult(BaseModel):
    success: bool
    exit_code: int | None
    stdout: str = ''
    stderr: str = ''
    timed_out: bool = False
    error_code: str | None = None
    command: list[str] = Field(default_factory=list)


def _as_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value or ''


class ControlledProcessRunner:
    def __init__(self, commands: Mapping[str, AllowedCommand]) -> None:
        self._commands = dict(commands)
        if not self._commands:
            raise ProcessPolicyError('subprocess 动作白名单不能为空')

    def execute(
        self,
        action: str,
        *,
        arguments: Sequence[str] = (),
        cwd: Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> ControlledProcessResult:
        specification = self._commands.get(action)
        if specification is None:
            raise ProcessPolicyError(f'动作未列入白名单：{action}')
        normalized_arguments = tuple(arguments)
        if any('\x00' in argument for argument in normalized_arguments):
            raise ProcessPolicyError('subprocess 参数包含非法空字符')
        if not specification.argument_policy(normalized_arguments):
            raise ProcessPolicyError(f'动作参数未通过白名单策略：{action}')
        working_directory = (cwd or specification.working_directory).resolve()
        allowed_root = specification.working_directory
        if working_directory != allowed_root and not working_directory.is_relative_to(allowed_root):
            raise ProcessPolicyError(f'工作目录超出白名单：{working_directory}')
        command = [
            str(specification.executable),
            *specification.fixed_arguments,
            *normalized_arguments,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=working_directory,
                env=dict(environment) if environment is not None else None,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=specification.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            return ControlledProcessResult(
                success=False,
                exit_code=None,
                stdout=_as_text(error.stdout),
                stderr=_as_text(error.stderr),
                timed_out=True,
                error_code='PROCESS_TIMEOUT',
                command=command,
            )
        except OSError as error:
            return ControlledProcessResult(
                success=False,
                exit_code=None,
                stderr=str(error),
                error_code='PROCESS_ERROR',
                command=command,
            )
        return ControlledProcessResult(
            success=completed.returncode == 0,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            error_code=None if completed.returncode == 0 else 'PROCESS_FAILED',
            command=command,
        )
