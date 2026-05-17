"""Inventory specialist (Fynd, BRD §9.2): stockout risk, slow movers,
cross-warehouse transfer recommendations."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import InventoryDigest


class InventoryAgent(BaseAgent[InventoryDigest]):
    output_schema = InventoryDigest
