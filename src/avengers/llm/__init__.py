"""LLM provider interface (spec §9.1).

Every model call goes through `LLMProvider`. Vendor SDKs are only imported
inside the adapter modules in this package — never elsewhere in the codebase.
"""

from avengers.llm.base import LLMProvider, LLMProviderError, LLMRegistry, get_registry
from avengers.llm.router import LLMRouter

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMRegistry",
    "LLMRouter",
    "get_registry",
]
