from pathlib import Path

import pytest

from avengers.memory.fs_memory import FilesystemMemory
from avengers.memory.in_memory_store import InMemoryStore, MemoryItem


async def test_in_memory_upsert_and_search():
    store = InMemoryStore()
    ns = "acme/u1/notes"
    await store.upsert(ns, [
        MemoryItem(id="1", text="quarterly revenue surged 20%"),
        MemoryItem(id="2", text="security incident in prod"),
        MemoryItem(id="3", text="quarterly hiring plan"),
    ])
    hits = await store.search(ns, "quarterly", k=5)
    assert {h.id for h in hits} == {"1", "3"}


async def test_namespace_isolation():
    store = InMemoryStore()
    await store.upsert("a/x/n", [MemoryItem(id="1", text="alpha")])
    await store.upsert("b/y/n", [MemoryItem(id="1", text="bravo")])
    assert (await store.get("a/x/n", "1")).text == "alpha"  # type: ignore[union-attr]
    assert (await store.get("b/y/n", "1")).text == "bravo"  # type: ignore[union-attr]
    assert await store.get("c/z/n", "1") is None


def test_fs_memory_safe_path(tmp_path: Path):
    fs = FilesystemMemory(tmp_path)
    fs.write("acme", "u1", "profile.md", "# user profile")
    assert fs.read("acme", "u1", "profile.md") == "# user profile"
    assert fs.list("acme", "u1") == ["profile.md"]
    fs.delete("acme", "u1", "profile.md")
    assert fs.read("acme", "u1", "profile.md") is None


def test_fs_memory_rejects_traversal(tmp_path: Path):
    fs = FilesystemMemory(tmp_path)
    with pytest.raises(ValueError):
        fs.read("acme", "u1", "../escape.md")
    with pytest.raises(ValueError):
        fs.read("acme", "u1/../other", "x.md")
