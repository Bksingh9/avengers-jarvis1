"""Content specialist (spec §10.6). Drafts allowed; publish needs approval."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import ContentDigest


class ContentAgent(BaseAgent[ContentDigest]):
    output_schema = ContentDigest
