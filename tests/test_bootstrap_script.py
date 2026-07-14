from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bootstrap-dev.ps1"


def test_windows_bootstrap_exposes_an_offline_self_test() -> None:
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("Windows PowerShell is not available")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-SelfTest",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Bootstrap self-test passed." in completed.stdout
    assert "Drive-root parent handling: passed" in completed.stdout
    assert "Validation checks: pytest, ruff, mypy, verify-all, version" in completed.stdout


def test_windows_bootstrap_accepts_portable_configuration(tmp_path: Path) -> None:
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("Windows PowerShell is not available")

    target = tmp_path / "portable-target"
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-SelfTest",
            "-Repository",
            "https://example.invalid/Other.git",
            "-Target",
            str(target),
            "-Branch",
            "feature/test",
            "-ExpectedCommit",
            "deadbeef",
            "-PythonCommand",
            "custom-python",
            "-CacheAttempts",
            "5",
            "-SkipValidation",
            "-SkipMathlibCache",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )

    output = completed.stdout.replace("\\", "/")
    assert completed.returncode == 0, output + completed.stderr
    assert "Repository: https://example.invalid/Other.git" in output
    assert f"Target: {target.as_posix()}" in output
    assert "Branch: feature/test" in output
    assert "Expected commit: deadbeef" in output
    assert "Python command: custom-python" in output
    assert "Cache attempts: 5" in output
    assert "Skip validation: True" in output
    required = output.split("Required commands: ", 1)[1].splitlines()[0]
    assert "custom-python" in required
    assert "curl.exe" not in required
    assert "tar.exe" not in required
    assert not target.exists()


def test_bootstrap_artifact_has_no_embedded_credentials_or_wildcard_trust() -> None:
    text = SCRIPT.read_text(encoding="utf-8").casefold()

    assert "github_pat_" not in text
    assert "ghp_" not in text
    assert "password=" not in text
    assert "safe.directory '*'" not in text
    assert "safe.directory=*" not in text


def _run_repository_only(
    powershell: str, repository: Path, target: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepositoryOnly",
            "-Repository",
            str(repository),
            "-Target",
            str(target),
            "-Branch",
            "main",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _git(*args: str | Path, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *(str(arg) for arg in args)],
        cwd=cwd,
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
    )


def test_repository_only_clones_fast_forwards_and_preserves_local_commits(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell")
    git = shutil.which("git")
    if powershell is None or git is None:
        pytest.skip("PowerShell and Git are required")

    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    target = tmp_path / "target"
    _git("init", "--bare", origin)
    _git("init", "--initial-branch=main", seed)
    _git("config", "user.name", "Bootstrap Test", cwd=seed)
    _git("config", "user.email", "bootstrap@example.invalid", cwd=seed)
    (seed / "first.txt").write_text("first\n", encoding="utf-8")
    _git("add", "first.txt", cwd=seed)
    _git("commit", "-m", "first", cwd=seed)
    _git("remote", "add", "origin", origin, cwd=seed)
    _git("push", "-u", "origin", "main", cwd=seed)

    cloned = _run_repository_only(powershell, origin, target)
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    assert "Repository synchronization passed" in cloned.stdout

    (seed / "second.txt").write_text("second\n", encoding="utf-8")
    _git("add", "second.txt", cwd=seed)
    _git("commit", "-m", "second", cwd=seed)
    _git("push", "origin", "main", cwd=seed)
    updated = _run_repository_only(powershell, origin, target)
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert (target / "second.txt").read_text(encoding="utf-8") == "second\n"

    _git("config", "user.name", "Bootstrap Test", cwd=target)
    _git("config", "user.email", "bootstrap@example.invalid", cwd=target)
    (target / "local.txt").write_text("local\n", encoding="utf-8")
    _git("add", "local.txt", cwd=target)
    _git("commit", "-m", "local", cwd=target)
    refused = _run_repository_only(powershell, origin, target)
    assert refused.returncode != 0
    assert "ahead of or diverged" in refused.stderr
    assert (target / "local.txt").exists()
