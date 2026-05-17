"""Memory-store Protocol (spec §9.2).

Namespaces map 1:1 to (tenant, user|"shared", purpose) tuples — e.g.
`acme/u123/profile`, `acme/shared/research-corpus`. Adapters must enforce
hard namespace isolation; cross-namespace reads are a bug.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class MemoryItem(BaseModel):
    """One stored record. `embedding` is provider-managed (None when not yet indexed)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime | None = None
    score: float | None = None  # populated by search()


class MemoryStore(Protocol):
    async def upsert(self, namespace: str, items: list[MemoryItem]) -> None: ...

    async def search(
        self,
        namespace: str,
        query: str,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryItem]: ...

    async def get(self, namespace: str, id: str) -> MemoryItem | None: ...

    async def delete(self, namespace: str, ids: list[str]) -> None: ...

    async def health(self) -> bool: ...
