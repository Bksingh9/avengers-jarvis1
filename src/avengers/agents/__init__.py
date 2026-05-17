"""Agent plane (spec §10).

Six reference specialists subclass `BaseAgent`. The `Director` orchestrates
fan-out and aggregation; it is itself an agent so the same audit/policy
machinery covers it.
"""

from avengers.agents.base import AgentDeps, AgentResult, BaseAgent
from avengers.agents.catalog import CatalogAgent
from avengers.agents.content import ContentAgent
from avengers.agents.director import Director, DirectorInput
from avengers.agents.inventory import InventoryAgent
from avengers.agents.markets import MarketsAgent
from avengers.agents.meetings import MeetingsAgent
from avengers.agents.operations import OperationsAgent
from avengers.agents.reconciliation import ReconciliationAgent
from avengers.agents.research import ResearchAgent
from avengers.agents.security import SecurityAgent

__all__ = [
    "AgentDeps",
    "AgentResult",
    "BaseAgent",
    "CatalogAgent",
    "ContentAgent",
    "Director",
    "DirectorInput",
    "InventoryAgent",
    "MarketsAgent",
    "MeetingsAgent",
    "OperationsAgent",
    "ReconciliationAgent",
    "ResearchAgent",
    "SecurityAgent",
]
