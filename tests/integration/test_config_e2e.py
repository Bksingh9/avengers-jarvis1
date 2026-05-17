"""Load the ACME tenant + research agent + connectors + policies from the
sample YAML — proves the shipped configs validate end-to-end."""

from pathlib import Path

from avengers.core.config_loader import ConfigStore


def test_sample_configs_load():
    repo_config = Path(__file__).resolve().parents[2] / "config"
    store = ConfigStore(repo_config)
    store.reload()

    t = store.tenant("acme")
    assert "research" in t.agents_enabled
    assert t.budgets.daily_usd_cap == 250

    a = store.agent("research")
    assert "exa_search" in a.tools.mcp
    assert "no_pii_to_external_search" in a.policies
    assert a.evals is not None and a.evals.gate_score == 0.85

    c = store.connector("exa_search")
    assert c.caching.ttl_seconds == 600

    policy_ids = {p.id for p in store.policies()}
    assert {"no_pii_to_external_search", "cite_every_claim", "block_writes"} <= policy_ids
