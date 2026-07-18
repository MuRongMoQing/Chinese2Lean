from __future__ import annotations

from pathlib import Path

from chinese2lean.application.composition import build_product_runtime

ROOT = Path(__file__).parents[1]


def test_product_runtime_uses_initialized_workspace_for_all_lean_execution(
    tmp_path: Path,
) -> None:
    initialized_workspace = tmp_path / "initialized-workspace"
    initialized_workspace.mkdir()
    initialized_elan_home = tmp_path / "initialized-elan"
    initialized_elan_home.mkdir()

    runtime = build_product_runtime(
        ROOT,
        storage_root=tmp_path / "storage",
        log_root=tmp_path / "logs",
        verification_root=initialized_workspace,
        elan_home=initialized_elan_home,
    )
    try:
        converter = runtime.service._converter
        verifier = runtime.service._verifier

        assert converter.project_root == ROOT.resolve()
        assert converter.runner is not None
        assert converter.runner.workspace == initialized_workspace.resolve()
        assert converter.runner.elan_home == initialized_elan_home.resolve()
        assert verifier.workspace == initialized_workspace.resolve()
        assert verifier.elan_home == initialized_elan_home.resolve()
    finally:
        for logger in runtime.loggers.values():
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
