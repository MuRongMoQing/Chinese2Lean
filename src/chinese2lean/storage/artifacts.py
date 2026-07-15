from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

ALLOWED_ARTIFACT_TYPES = frozenset({".lean", ".ir.json", ".report.json"})


@dataclass(frozen=True, slots=True)
class Artifact:
    id: str
    artifact_type: str
    storage_name: str
    path: Path


@dataclass(frozen=True, slots=True)
class Upload:
    id: str
    original_name: str
    storage_name: str
    path: Path
    text: str
    size: int


class ArtifactStorage:
    def __init__(self, root: Path, *, max_upload_bytes: int = 1_048_576) -> None:
        if max_upload_bytes <= 0:
            raise ValueError("Upload size limit must be positive")
        self.root = Path(root).resolve()
        self.upload_root = (self.root / "uploads").resolve()
        self.max_upload_bytes = max_upload_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, *, artifact_type: str, content: str) -> Artifact:
        if artifact_type not in ALLOWED_ARTIFACT_TYPES:
            raise ValueError("Unsupported artifact type")
        artifact_id = str(uuid4())
        storage_name = f"{artifact_id}{artifact_type}"
        path = self._safe_path(self.root, storage_name)
        path.write_text(content, encoding="utf-8")
        return Artifact(
            id=artifact_id,
            artifact_type=artifact_type,
            storage_name=storage_name,
            path=path,
        )

    def read(self, artifact_id: str) -> bytes:
        normalized_id = self._validated_uuid(artifact_id)
        for artifact_type in ALLOWED_ARTIFACT_TYPES:
            path = self._safe_path(self.root, f"{normalized_id}{artifact_type}")
            if path.is_file():
                return path.read_bytes()
        raise FileNotFoundError("Artifact does not exist")

    def save_upload(self, filename: str, content: bytes) -> Upload:
        self._validate_client_filename(filename)
        if len(content) > self.max_upload_bytes:
            raise ValueError("Upload exceeds the configured size limit")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Upload must be valid UTF-8 text") from error

        upload_id = str(uuid4())
        storage_name = f"{upload_id}{Path(filename).suffix.lower()}"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        path = self._safe_path(self.upload_root, storage_name)
        path.write_bytes(content)
        return Upload(
            id=upload_id,
            original_name=filename,
            storage_name=storage_name,
            path=path,
            text=text,
            size=len(content),
        )

    @staticmethod
    def _safe_path(root: Path, storage_name: str) -> Path:
        if Path(storage_name).name != storage_name:
            raise ValueError("Storage name must not contain a path")
        path = (root / storage_name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Storage path escaped the configured root")
        return path

    @staticmethod
    def _validated_uuid(value: str) -> str:
        if Path(value).name != value or Path(value).is_absolute() or ".." in value:
            raise ValueError("Artifact id must be a server-generated UUID")
        try:
            parsed = UUID(value)
        except ValueError as error:
            raise ValueError("Artifact id must be a server-generated UUID") from error
        normalized = str(parsed)
        if normalized != value:
            raise ValueError("Artifact id must be a canonical UUID")
        return normalized

    @staticmethod
    def _validate_client_filename(filename: str) -> None:
        path = Path(filename)
        if (
            not filename
            or path.is_absolute()
            or path.name != filename
            or ".." in filename
            or "/" in filename
            or "\\" in filename
        ):
            raise ValueError("Upload filename must be a safe base filename")
