import json
import os
import tempfile
from pathlib import Path

from src.models import TrendingSnapshot
from src.storage.supabase_client import SupabaseStorage


def save_file_snapshot(path: Path, snapshot: TrendingSnapshot, curated_names: list[str]) -> None:
    """Atomically replace a portable snapshot; never serialize settings or credentials."""
    payload = snapshot.model_dump(mode="json")
    payload["curated_repositories"] = curated_names
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


__all__ = ["SupabaseStorage", "save_file_snapshot"]
