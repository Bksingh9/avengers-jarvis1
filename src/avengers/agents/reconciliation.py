"""Reconciliation specialist (Fynd, BRD §9.2): settlement mismatches across
marketplaces, GST anomalies, returns liability accruals."""

from avengers.agents.base import BaseAgent
from avengers.schemas.brief import ReconciliationDigest


class ReconciliationAgent(BaseAgent[ReconciliationDigest]):
    output_schema = ReconciliationDigest
