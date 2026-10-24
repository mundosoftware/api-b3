"""Local-only cache and artifact helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = PROJECT_ROOT / ".cache" / "jev-post-forecast"
DEFAULT_ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "jev-post-forecast"


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        result = json.load(handle)
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return result


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


class JsonCache:
    def __init__(self, root: Path = DEFAULT_CACHE_DIR, *, offline: bool = False, refresh: bool = False):
        self.root = root
        self.offline = offline
        self.refresh = refresh

    def path(self, namespace: str, key: Any) -> Path:
        return self.root / namespace / f"{stable_hash(key)}.json"

    def get(self, namespace: str, key: Any) -> dict[str, Any] | None:
        path = self.path(namespace, key)
        if self.refresh or not path.exists():
            return None
        return load_json(path)

    def put(self, namespace: str, key: Any, value: dict[str, Any]) -> None:
        write_json(self.path(namespace, key), value)

    def require(self, namespace: str, key: Any) -> dict[str, Any]:
        value = self.get(namespace, key)
        if value is None:
            raise FileNotFoundError(f"Offline cache miss for {namespace}: {stable_hash(key)[:12]}")
        return value
