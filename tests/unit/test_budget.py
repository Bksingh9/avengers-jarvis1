from datetime import date

import pytest

from avengers.core.budget import BudgetExceededError, BudgetTracker


async def test_charges_accumulate():
    b = BudgetTracker()
    d = date(2026, 5, 17)
    await b.try_charge(tenant_id="acme", user_id="u1", cost_usd=0.10, daily_cap=1.0, per_user_cap=0.5, for_date=d)
    await b.try_charge(tenant_id="acme", user_id="u1", cost_usd=0.20, daily_cap=1.0, per_user_cap=0.5, for_date=d)
    snap = await b.snapshot("acme", for_date=d)
    assert snap.tenant_spend_usd == pytest.approx(0.30)
    assert snap.per_user_spend_usd["u1"] == pytest.approx(0.30)


async def test_user_cap_trips():
    b = BudgetTracker()
    d = date(2026, 5, 17)
    await b.try_charge(tenant_id="acme", user_id="u1", cost_usd=0.40, daily_cap=10.0, per_user_cap=0.5, for_date=d)
    with pytest.raises(BudgetExceededError) as ei:
        await b.try_charge(tenant_id="acme", user_id="u1", cost_usd=0.20, daily_cap=10.0, per_user_cap=0.5, for_date=d)
    assert "user:" in ei.value.scope


async def test_tenant_cap_trips():
    b = BudgetTracker()
    d = date(2026, 5, 17)
    await b.try_charge(tenant_id="acme", user_id="u1", cost_usd=0.6, daily_cap=1.0, per_user_cap=None, for_date=d)
    with pytest.raises(BudgetExceededError) as ei:
        await b.try_charge(tenant_id="acme", user_id="u2", cost_usd=0.5, daily_cap=1.0, per_user_cap=None, for_date=d)
    assert ei.value.scope.startswith("tenant:")


async def test_failed_charge_does_not_persist():
    b = BudgetTracker()
    d = date(2026, 5, 17)
    with pytest.raises(BudgetExceededError):
        await b.try_charge(tenant_id="acme", user_id="u", cost_usd=2.0, daily_cap=1.0, per_user_cap=1.0, for_date=d)
    snap = await b.snapshot("acme", for_date=d)
    assert snap.tenant_spend_usd == 0.0
