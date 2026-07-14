import json
from pathlib import Path

from typer.testing import CliRunner

from chinese2lean.cli import app

ROOT = Path(__file__).parents[1]


def test_normalize_and_version_commands_expose_auditable_metadata() -> None:
    normalized = CliRunner().invoke(
        app,
        ["normalize", str(ROOT / "examples" / "chinese" / "positive_add_one.md")],
    )
    assert normalized.exit_code == 0, normalized.output
    payload = json.loads(normalized.output)
    assert payload["source_text"]
    assert payload["normalized_text"]
    assert isinstance(payload["mappings"], list)

    version = CliRunner().invoke(app, ["version"])
    assert version.exit_code == 0, version.output
    versions = json.loads(version.output)
    assert versions["lean_version"] == "4.19.0"
    assert versions["dictionary_version"] == "0.1.0"


def test_verify_all_command_is_registered() -> None:
    help_result = CliRunner().invoke(app, ["verify-all", "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "DIRECTORY" in help_result.output.upper()
