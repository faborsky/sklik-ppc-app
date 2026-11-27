"""Offline tests for retargeting --detail (audience size via lists.get)."""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklik.commands import retargeting  # noqa: E402
from test_fixes import ns, run  # noqa: E402


class TestRetargetingDetail(unittest.TestCase):
    def _fake(self, n):
        calls = []

        def fake(method, params, uid=None, **kw):
            calls.append((method, params))
            if method == "retargeting.lists.list":
                return {"lists": [{"listId": i, "name": f"L{i}", "status": "active",
                                   "deleted": False} for i in range(n)]}
            return {"lists": [{"listId": i, "attributes": {"users": i * 10, "membership": 30,
                                                           "takeAllUsers": False},
                               "conditionGroups": [{"conditions": [{"type": "contains",
                                                                    "value": "x.cz"}]}]}
                              for i in params[0]]}
        return fake, calls

    def test_detail_adds_size_in_chunks_of_100(self):
        fake, calls = self._fake(150)
        with mock.patch.object(retargeting, "_api_call", side_effect=fake):
            out, code = run(retargeting.cmd_retargeting, ns(detail=True))
        self.assertIsNone(code)
        gets = [p[0] for m, p in calls if m == "retargeting.lists.get"]
        self.assertEqual([len(g) for g in gets], [100, 50])
        res = json.loads(out)
        self.assertEqual(res[7]["users"], 70)
        self.assertEqual(res[7]["conditionGroups"], [[{"type": "contains", "value": "x.cz"}]])

    def test_without_detail_no_lists_get(self):
        fake, calls = self._fake(3)
        with mock.patch.object(retargeting, "_api_call", side_effect=fake):
            out, _ = run(retargeting.cmd_retargeting, ns(detail=False))
        self.assertEqual([m for m, _ in calls], ["retargeting.lists.list"])
        self.assertNotIn("users", json.loads(out)[0])


if __name__ == "__main__":
    unittest.main()
