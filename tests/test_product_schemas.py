import pytest
from pydantic import ValidationError

from chinese2lean.application.models import ConvertResponse, ProductVersion


def test_product_version_exposes_every_locked_product_component() -> None:
    version = ProductVersion(
        chinese2lean_version="0.1.0",
        core_version="0.1.0",
        desktop_version="0.1.0",
        web_version="0.1.0",
        lean_version="4.19.0",
        mathlib_revision="c44e0c8",
        dictionary_version="0.1.0",
        ir_schema_version="1",
    )

    assert tuple(version.model_dump()) == (
        "chinese2lean_version",
        "core_version",
        "desktop_version",
        "web_version",
        "lean_version",
        "mathlib_revision",
        "dictionary_version",
        "ir_schema_version",
    )


def test_convert_response_rejects_lowercase_core_status() -> None:
    with pytest.raises(ValidationError):
        ConvertResponse(status="verified", lean="", ir={})
