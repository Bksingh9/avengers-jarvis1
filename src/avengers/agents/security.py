"""Security specialist (spec §10.4). Acknowledge/close always needs approval."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import SecurityDigest


class SecurityAgent(BaseAgent[SecurityDigest]):
    output_schema = SecurityDigest
