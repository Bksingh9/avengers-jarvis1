"""Process-local memory store. Tests + dev only — no persistence, no real ANN.

Search ranks by simple lowercased substring overlap; good enough for tests
and to exercise the API surface without standing up a vector DB.
"""

from __future__ import annotations

import asyncio
from typing import Any

from avengers.memory.base import MemoryItem, MemoryStore


class InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._data: dict[str, dict[str, MemoryItem]] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, namespace: str, items: list[MemoryItem]) -> None:
        async with self._lock:
            bucket = self._data.setdefault(namespace, {})
            for it in items:
                bucket[it.id] = it

    async def search(
        self,
        namespace: str,
        query: str,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryItem]:
        q = query.lower()
        async with self._lock:
            bucket = self._data.get(namespace, {})
            candidates = list(bucket.values())
        if filters:
            candidates = [c for c in candidates if all(c.metadata.get(k) == v for k, v in filters.items())]
        scored: list[tuple[float, MemoryItem]] = []
        for item in candidates:
            text = item.text.lower()
            if q in text:
                score = q.count(" ") + 1 + len(q) / max(len(text), 1)
                scored.append((score, item.model_copy(update={"score": score})))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [it for _, it in scored[:k]]

    async def get(self, namespace: str, id: str) -> MemoryItem | None:
        async with self._lock:
            return self._data.get(namespace, {}).get(id)

    async def delete(self, namespace: str, ids: list[str]) -> None:
        async with self._lock:
            bucket = self._data.get(namespace, {})
            for i in ids:
                bucket.pop(i, None)

    async def health(self) -> bool:
        return True
