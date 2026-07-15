from datetime import UTC
from pathlib import Path
from uuid import UUID

import pytest

from chinese2lean.storage import HistoryStore


def test_history_store_saves_lists_and_reads_complete_records(tmp_path) -> None:
    store = HistoryStore(tmp_path / "history.sqlite3", tmp_path / "artifacts")

    saved = store.save(
        input_text="对任意自然数 n，n + 1 > n。",
        status="VERIFIED",
        output={"lean": "theorem positive_add_one : ∀ n : ℕ, n + 1 > n := by omega"},
        versions={"lean": "4.19.0", "mathlib": "c44e0c8"},
    )

    assert saved.id > 0
    assert saved.created_at.tzinfo is UTC
    assert store.get(saved.id) == saved
    assert store.list() == [saved]
    assert store.get(saved.id + 1) is None


@pytest.mark.parametrize("artifact_type", [".lean", ".ir.json", ".report.json"])
def test_artifacts_use_server_uuid_names_under_the_configured_root(
    tmp_path, artifact_type: str
) -> None:
    artifact_root = tmp_path / "artifacts"
    store = HistoryStore(tmp_path / "history.sqlite3", artifact_root)
    history = store.save(input_text="input", status="GENERATED", output={}, versions={})

    artifact = store.save_artifact(
        history.id,
        artifact_type=artifact_type,
        content="generated text",
    )

    UUID(artifact.id)
    assert artifact.artifact_type == artifact_type
    assert Path(artifact.storage_name).name == artifact.storage_name
    assert artifact.storage_name == f"{artifact.id}{artifact_type}"
    assert artifact.path.parent == artifact_root.resolve()
    assert store.read_artifact(artifact.id) == b"generated text"


@pytest.mark.parametrize(
    "unsafe_type",
    [".txt", "result.lean", "../result.lean", "/tmp/result.lean"],
)
def test_artifacts_reject_unknown_types_and_client_paths(tmp_path, unsafe_type: str) -> None:
    store = HistoryStore(tmp_path / "history.sqlite3", tmp_path / "artifacts")
    history = store.save(input_text="input", status="GENERATED", output={}, versions={})

    with pytest.raises(ValueError, match="artifact type"):
        store.save_artifact(history.id, artifact_type=unsafe_type, content="text")


@pytest.mark.parametrize("unsafe_id", ["../secret", "/tmp/secret", "not-a-uuid"])
def test_artifact_reads_reject_client_paths(tmp_path, unsafe_id: str) -> None:
    store = HistoryStore(tmp_path / "history.sqlite3", tmp_path / "artifacts")

    with pytest.raises(ValueError, match="UUID"):
        store.read_artifact(unsafe_id)


def test_upload_accepts_only_bounded_utf8_text_with_safe_server_name(tmp_path) -> None:
    artifact_root = tmp_path / "artifacts"
    store = HistoryStore(
        tmp_path / "history.sqlite3",
        artifact_root,
        max_upload_bytes=12,
    )

    upload = store.save_upload("命题.md", "自然数".encode())

    UUID(upload.id)
    assert upload.original_name == "命题.md"
    assert upload.storage_name == f"{upload.id}.md"
    assert upload.path.parent == (artifact_root / "uploads").resolve()
    assert upload.text == "自然数"
    assert upload.size == 9

    with pytest.raises(ValueError, match="UTF-8"):
        store.save_upload("bad.txt", b"\xff")
    with pytest.raises(ValueError, match="size"):
        store.save_upload("large.md", b"x" * 13)


@pytest.mark.parametrize("unsafe_name", ["../input.md", "folder/input.md", "/tmp/input.md"])
def test_upload_rejects_paths_instead_of_trusting_client_filenames(
    tmp_path, unsafe_name: str
) -> None:
    store = HistoryStore(tmp_path / "history.sqlite3", tmp_path / "artifacts")

    with pytest.raises(ValueError, match="filename"):
        store.save_upload(unsafe_name, b"safe text")
