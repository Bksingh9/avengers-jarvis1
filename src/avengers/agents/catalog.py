"""Catalog specialist (Fynd, BRD §9.2): flagged listings, missing attributes,
pricing-vs-MAP violations."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import CatalogDigest


class CatalogAgent(BaseAgent[CatalogDigest]):
    output_schema = CatalogDigest
