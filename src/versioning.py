import os
import re
import subprocess
from pathlib import Path


RELEASE_TAG_PATTERN = re.compile(
    r"^RELEASE_(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)
UNKNOWN_RELEASE_TAG = "RELEASE_0.0.0"


def validate_release_tag(tag: str) -> str:
    normalized = tag.strip()
    if RELEASE_TAG_PATTERN.fullmatch(normalized) is None:
        raise ValueError("release tag must follow RELEASE_1.2.0")
    return normalized


def detect_release_tag(repository_root: Path | None = None) -> str:
    configured = os.getenv("PANEL_RELEASE_TAG")
    if configured:
        return validate_release_tag(configured)

    root = repository_root or Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            [
                "git",
                "describe",
                "--tags",
                "--match",
                "RELEASE_*",
                "--abbrev=0",
                "HEAD",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return validate_release_tag(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return UNKNOWN_RELEASE_TAG


def display_version_from_release_tag(tag: str) -> str:
    validated = validate_release_tag(tag)
    return f"v.{validated.removeprefix('RELEASE_')}"
