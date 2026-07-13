from typer.testing import CliRunner

from chinese2lean.cli import app


def test_terminology_lookup_is_safe_on_legacy_windows_console() -> None:
    result = CliRunner().invoke(app, ["terminology", "lookup", "任意"])
    assert result.exit_code == 0, result.output
    assert "logic.forall" in result.output
    assert "\\u2200" in result.output
