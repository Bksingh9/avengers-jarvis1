"""Research specialist (spec §10.5)."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import ResearchDigest


class ResearchAgent(BaseAgent[ResearchDigest]):
    output_schema = ResearchDigest
