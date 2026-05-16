"""PII redaction used by audit + the `no_pii_to_external_search` policy.

Conservative regex-based detector. Production deployments should swap in a
proper detector (e.g. Microsoft Presidio) by re-binding `RedactionEngine` in DI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
# US SSN ###-##-####:
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# 13-19 digit card-like sequences (with optional separators):
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
# Indian PAN: 5 letters + 4 digits + 1 letter
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
# Indian Aadhaar 12 digits (loose):
_AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")

# Order matters: specific patterns (SSN, PAN, Aadhaar, card) must run before
# the broad PHONE pattern, otherwise PHONE's loose digit run would gobble them.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", _EMAIL_RE),
    ("SSN", _SSN_RE),
    ("PAN", _PAN_RE),
    ("CARD", _CARD_RE),
    ("AADHAAR", _AADHAAR_RE),
    ("PHONE", _PHONE_RE),
]


@dataclass(frozen=True, slots=True)
class RedactionResult:
    text: str
    hits: dict[str, int]

    @property
    def has_pii(self) -> bool:
        return bool(self.hits)


def redact(text: str) -> RedactionResult:
    hits: dict[str, int] = {}
    out = text
    for label, pat in _PATTERNS:
        count = 0

        def _sub(_m: re.Match[str], _label: str = label) -> str:
            nonlocal count
            count += 1
            return f"<{_label}>"

        out = pat.sub(_sub, out)
        if count:
            hits[label] = count
    return RedactionResult(text=out, hits=hits)


def contains_pii(text: str) -> bool:
    """Fast yes/no check used by policy conditions."""
    return any(pat.search(text) for _, pat in _PATTERNS)
