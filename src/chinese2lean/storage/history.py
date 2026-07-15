from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chinese2lean.storage.artifacts import Artifact, ArtifactStorage, Upload


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    id: int
    input_text: str
    created_at: datetime
    status: str
    output: dict[str, Any]
    versions: dict[str, str]


class HistoryStore:
    def __init__(
        self,
        database_path: Path,
        artifact_root: Path,
        *,
        max_upload_bytes: int = 1_048_576,
    ) -> None:
        self.database_path = Path(database_path)
        self.artifact_root = Path(artifact_root)
        self.max_upload_bytes = max_upload_bytes
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._artifacts = ArtifactStorage(
            self.artifact_root,
            max_upload_bytes=max_upload_bytes,
        )
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    input_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    versions_json TEXT NOT NULL
                )
                """
            )

    def save(
        self,
        *,
        input_text: str,
        status: str,
        output: Mapping[str, Any],
        versions: Mapping[str, str],
    ) -> HistoryRecord:
        created_at = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO history (input_text, created_at, status, output_json, versions_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    input_text,
                    created_at.isoformat(),
                    status,
                    json.dumps(dict(output), ensure_ascii=False),
                    json.dumps(dict(versions), ensure_ascii=False),
                ),
            )
            record_id = cursor.lastrowid
        if record_id is None:
            raise RuntimeError("SQLite did not return an id for the saved history record")
        return HistoryRecord(
            id=record_id,
            input_text=input_text,
            created_at=created_at,
            status=status,
            output=dict(output),
            versions=dict(versions),
        )

    def list(self) -> list[HistoryRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
        return [self._record_from_row(row) for row in rows]

    def get(self, record_id: int) -> HistoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM history WHERE id = ?", (record_id,)
            ).fetchone()
        return None if row is None else self._record_from_row(row)

    def save_artifact(
        self,
        record_id: int,
        *,
        artifact_type: str,
        content: str,
    ) -> Artifact:
        if self.get(record_id) is None:
            raise ValueError("History record does not exist")
        return self._artifacts.save(artifact_type=artifact_type, content=content)

    def read_artifact(self, artifact_id: str) -> bytes:
        return self._artifacts.read(artifact_id)

    def save_upload(self, filename: str, content: bytes) -> Upload:
        return self._artifacts.save_upload(filename, content)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> HistoryRecord:
        output = json.loads(row["output_json"])
        versions = json.loads(row["versions_json"])
        if not isinstance(output, dict) or not isinstance(versions, dict):
            raise ValueError("Invalid history data in SQLite")
        return HistoryRecord(
            id=row["id"],
            input_text=row["input_text"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"],
            output=output,
            versions=versions,
        )
