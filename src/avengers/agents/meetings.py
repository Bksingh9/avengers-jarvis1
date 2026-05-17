"""Meetings specialist (spec §10.2)."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import MeetingDigest


class MeetingsAgent(BaseAgent[MeetingDigest]):
    output_schema = MeetingDigest
