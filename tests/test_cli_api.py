from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from chinese2lean.api.app import app as api_app
from chinese2lean.cli import app

ROOT = Path(__file__).parents[1]


def test_cli_parse_writes_ir(tmp_path: Path) -> None:
    output = tmp_path / "theorem.json"
    result = CliRunner().invoke(
        app,
        [
            "parse",
            str(ROOT / "examples" / "positive_add_one.md"),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"theorem_name": "positive_add_one"' in output.read_text(encoding="utf-8")


def test_api_parse_and_health() -> None:
    client = TestClient(api_app)
    assert client.get("/health").json() == {"status": "ok"}
    source = (ROOT / "examples" / "positive_add_one.md").read_text(encoding="utf-8")
    response = client.post("/parse", json={"text": source, "verify": False})
    assert response.status_code == 200
    assert response.json()["ir"]["theorem_name"] == "positive_add_one"
