"""Markets specialist (spec §10.3)."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import MarketDigest


class MarketsAgent(BaseAgent[MarketDigest]):
    output_schema = MarketDigest
