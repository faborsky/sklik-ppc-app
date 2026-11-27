"""Offline tests for budget-check (spend vs daily budget)."""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklik.commands import budgets  # noqa: E402
from test_fixes import ns, run  # noqa: E402


def _days(n: int) -> list[str]:
    end = datetime.now() - timedelta(days=1)
    return [(end - timedelta(days=n - 1 - i)).strftime("%Y%m%d") for i in range(n)]


class TestBudgetCheck(unittest.TestCase):
    def _run(self, campaigns, report, **kw):
        args = ns(days=7, threshold=90, min_days=2, include_today=False, all=False)
        for k, v in kw.items():
            setattr(args, k, v)
        with mock.patch.object(budgets, "_fetch_all", return_value=campaigns), \
                mock.patch.object(budgets, "_fetch_report", return_value=report):
            out, code = run(budgets.cmd_budget_check, args)
        self.assertIsNone(code)
        return json.loads(out)

    def test_capped_campaign_is_flagged_even_with_api_zero(self):
        d = _days(7)
        camps = [{"id": 1, "name": "A", "status": "active", "budget": {"id": 10, "dayBudget": 10000}},
                 {"id": 2, "name": "B", "status": "active", "budget": {"id": 20, "dayBudget": 10000}}]
        report = [
            {"id": 1, "stats": [{"date": int(x), "totalMoney": 9900, "exhaustedBudgetShare": 0,
                                 "missImpressions": 0} for x in d]},
            {"id": 2, "stats": [{"date": int(x), "totalMoney": 3000} for x in d]},
        ]
        res = self._run(camps, report)
        self.assertEqual(res["limitedCount"], 1)
        self.assertEqual(res["campaigns"][0]["id"], 1)
        self.assertEqual(res["campaigns"][0]["daysAtCap"], 7)
        self.assertEqual(res["campaigns"][0]["apiFlagMax"], 0)

    def test_shared_budget_pools_spend(self):
        d = _days(7)
        camps = [{"id": 1, "name": "A", "status": "active", "budget": {"id": 10, "dayBudget": 10000}},
                 {"id": 2, "name": "B", "status": "active", "budget": {"id": 10, "dayBudget": 10000}}]
        report = [{"id": c, "stats": [{"date": int(x), "totalMoney": 5000} for x in d]} for c in (1, 2)]
        res = self._run(camps, report)
        self.assertEqual(res["limitedCount"], 1)
        self.assertEqual(res["campaigns"][0]["scope"], "shared")

    def test_paused_and_budgetless_are_skipped(self):
        camps = [{"id": 1, "name": "A", "status": "suspend", "budget": {"id": 10, "dayBudget": 10000}},
                 {"id": 2, "name": "B", "status": "active", "budget": {"id": 20, "dayBudget": 0}}]
        res = self._run(camps, [], all=True)
        self.assertEqual(res["checkedCount"], 0)
        self.assertEqual(res["skippedNoDayBudget"], 1)


if __name__ == "__main__":
    unittest.main()
