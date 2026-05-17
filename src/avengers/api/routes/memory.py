"""Memory / RAG API — ingest, search, delete.

The vector store behind this is the `MemoryStore` Protocol's active
implementation. In dev that's `InMemoryStore`; in production it's pgvector
or Turbopuffer/Pinecone — same routes either way.

LangChain-style usage from an agent:
    hits = container.vector_memory.search(namespace, query, k=5)
    context = "\\n".join(f"- {h.text}" for h in hits)
    -> include `context` in the LLM prompt

This is the lightweight RAG path. For richer retrieval (re-ranking,
hybrid keyword+vector, MMR), the same Protocol can be swapped for a
fuller implementation without touching agents/.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_tenant_ctx
from avengers.core.tenant import TenantContext
from avengers.memory.base import MemoryItem

router = APIRouter(prefix="/tenants/{tenant_id}/memory", tags=["memory"])


def _namespace(tenant_id: str, user_id: str | None, purpose: str = "rag") -> str:
    return f"{tenant_id}/{user_id or 'shared'}/{purpose}"


def _require_vector_store(container: AppContainer) -> None:
    if container.vector_memory is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Vector memory not configured. Bind a MemoryStore in bootstrap.",
        )


def _chunk_text(text: str, max_chars: int = 1_200, overlap: int = 200) -> list[str]:
    """Split a doc into overlapping windows. Naive char-based — good enough
    for the demo. Production wants tiktoken-based chunking for better
    boundaries."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    i = 0
    while i < len(text):
        end = min(i + max_chars, len(text))
        # Try to break at a paragraph or sentence boundary near the end
        if end < len(text):
            window = text[i:end]
            split_at = max(window.rfind("\n\n"), window.rfind(". "))
            if split_at > max_chars // 2:
                end = i + split_at + 1
        chunks.append(text[i:end].strip())
        i = end - overlap if end - overlap > i else end
    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(default="rag", pattern=r"^[a-z0-9_-]+$")
    text: str = Field(..., min_length=1, max_length=2_000_000)
    source: str = Field(..., description="Where this came from — URL, file path, etc.")
    metadata: dict = Field(default_factory=dict)


class IngestResponse(BaseModel):
    namespace: str
    source: str
    chunks: int
    item_ids: list[str]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = "rag"
    query: str = Field(..., min_length=1, max_length=2_000)
    k: int = Field(default=5, ge=1, le=50)
    filters: dict | None = None


class SearchHit(BaseModel):
    id: str
    text: str
    score: float | None
    source: str | None
    metadata: dict


class SearchResponse(BaseModel):
    namespace: str
    query: str
    hits: list[SearchHit]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest(
    body: IngestRequest,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> IngestResponse:
    """Chunk + store a document in the tenant's vector namespace.

    Embeddings are computed inside the `MemoryStore.upsert` adapter — for
    `InMemoryStore` we leave them None (search uses lexical matching);
    for `PgVectorStore` / Turbopuffer the embed call happens there.

    Idempotent on (source, content_hash): re-ingesting the same source +
    same text produces the same item IDs, overwriting in place.
    """
    _require_vector_store(container)
    user_id = ctx.user.id if ctx.user else None
    ns = _namespace(ctx.tenant_id, user_id, body.purpose)
    chunks = _chunk_text(body.text)
    if not chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no usable text after chunking")

    items: list[MemoryItem] = []
    for idx, chunk in enumerate(chunks):
        h = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
        item_id = f"{_slug(body.source)}__{idx}__{h}"
        items.append(MemoryItem(
            id=item_id,
            text=chunk,
            metadata={
                **body.metadata,
                "source": body.source,
                "chunk_idx": idx,
                "ingested_at": datetime.now(UTC).isoformat(),
            },
        ))

    await container.vector_memory.upsert(ns, items)
    return IngestResponse(
        namespace=ns,
        source=body.source,
        chunks=len(items),
        item_ids=[i.id for i in items],
    )


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> SearchResponse:
    """Vector / lexical search inside the tenant's namespace. Returns top-k."""
    _require_vector_store(container)
    user_id = ctx.user.id if ctx.user else None
    ns = _namespace(ctx.tenant_id, user_id, body.purpose)

    hits = await container.vector_memory.search(ns, body.query, k=body.k, filters=body.filters)
    return SearchResponse(
        namespace=ns,
        query=body.query,
        hits=[
            SearchHit(
                id=h.id,
                text=h.text,
                score=h.score,
                source=h.metadata.get("source") if h.metadata else None,
                metadata=h.metadata or {},
            )
            for h in hits
        ],
    )


@router.delete("/items")
async def delete_items(
    ids: list[str],
    purpose: Annotated[str, "rag"],
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    """Delete specific items from the tenant's namespace."""
    _require_vector_store(container)
    user_id = ctx.user.id if ctx.user else None
    ns = _namespace(ctx.tenant_id, user_id, purpose)
    await container.vector_memory.delete(ns, ids)
    return {"deleted": len(ids), "namespace": ns}


def _slug(text: str) -> str:
    """Safe-for-id slug of any text."""
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip().lower())
    return s[:64] or "unsourced"
