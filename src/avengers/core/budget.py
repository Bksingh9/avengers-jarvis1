"""Per-tenant / per-user cost cap tracker (spec §7.1 budgets).

In-process counter; production binds a Redis-backed implementation. Caps are
enforced *before* a model call by `try_charge()`; routers refuse to dispatch
if the call would breach the cap.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime


@dataclass(slots=True)
class BudgetSnapshot:
    tenant_id: str
    for_date: date
    tenant_spend_usd: float
    per_user_spend_usd: dict[str, float] = field(default_factory=dict)


class BudgetExceededError(RuntimeError):
    def __init__(self, scope: str, spent: float, cap: float) -> None:
        super().__init__(f"budget exceeded: {scope} spent={spent:.4f} cap={cap:.4f}")
        self.scope = scope
        self.spent = spent
        self.cap = cap


class BudgetTracker:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._daily: dict[tuple[str, date], float] = defaultdict(float)
        self._user_daily: dict[tuple[str, str, date], float] = defaultdict(float)

    async def try_charge(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        cost_usd: float,
        daily_cap: float,
        per_user_cap: float | None = None,
        for_date: date | None = None,
    ) -> None:
        d = for_date or datetime.now(UTC).date()
        async with self._lock:
            tenant_new = self._daily[(tenant_id, d)] + cost_usd
            if tenant_new > daily_cap:
                raise BudgetExceededError(f"tenant:{tenant_id}", tenant_new, daily_cap)
            user_new: float | None = None
            if user_id is not None and per_user_cap is not None:
                user_new = self._user_daily[(tenant_id, user_id, d)] + cost_usd
                if user_new > per_user_cap:
                    raise BudgetExceededError(
                        f"user:{tenant_id}/{user_id}", user_new, per_user_cap
                    )
            self._daily[(tenant_id, d)] = tenant_new
            if user_id is not None and user_new is not None:
                self._user_daily[(tenant_id, user_id, d)] = user_new

    async def snapshot(self, tenant_id: str, for_date: date | None = None) -> BudgetSnapshot:
        d = for_date or datetime.now(UTC).date()
        async with self._lock:
            users = {
                u: amt
                for (t, u, dd), amt in self._user_daily.items()
                if t == tenant_id and dd == d
            }
            return BudgetSnapshot(
                tenant_id=tenant_id,
                for_date=d,
                tenant_spend_usd=self._daily.get((tenant_id, d), 0.0),
                per_user_spend_usd=users,
            )
