"""Agent-SDK-style filesystem memory — `/memories/<user>/*.md` snapshots.

Used by the morning-brief workflow to read yesterday's brief and the user's
profile (spec §11.1 step 3). Stored as plain markdown so humans can audit.
"""

from __future__ import annotations

from pathlib import Path

# Constrain filenames to a safe charset; any path separator is rejected.
_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


class FilesystemMemory:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str, user_id: str, name: str) -> Path:
        for part in (tenant_id, user_id, name):
            if not part or any(c not in _SAFE_CHARS for c in part):
                raise ValueError(f"unsafe memory path component: {part!r}")
        out = self._root / tenant_id / user_id / name
        out.parent.mkdir(parents=True, exist_ok=True)
        # Defence in depth: confirm the resolved path is still inside root.
        if self._root not in out.resolve().parents:
            raise ValueError("memory path escapes root")
        return out

    def read(self, tenant_id: str, user_id: str, name: str) -> str | None:
        p = self._path(tenant_id, user_id, name)
        if not p.exists():
            return None
        return p.read_text()

    def write(self, tenant_id: str, user_id: str, name: str, content: str) -> None:
        self._path(tenant_id, user_id, name).write_text(content)

    def delete(self, tenant_id: str, user_id: str, name: str) -> None:
        p = self._path(tenant_id, user_id, name)
        p.unlink(missing_ok=True)

    def list(self, tenant_id: str, user_id: str) -> list[str]:
        d = self._root / tenant_id / user_id
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_file())
