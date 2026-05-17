"""Operations specialist (spec §10.7). v1 is read-only — no allowed writes."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import OpsDigest


class OperationsAgent(BaseAgent[OpsDigest]):
    output_schema = OpsDigest
