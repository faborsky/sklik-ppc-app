"""Offline tests for `lookalike-create` and `nakupy-item-stats`.

No network: the API entry points are patched. Run from the project root:

    source venv/bin/activate && python -m unittest discover -s tests -v
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sklik.api as api  # noqa: E402
from sklik.commands import nakupy, retargeting as rt  # noqa: E402


def ns(**kw: object) -> argparse.Namespace:
    kw.setdefault("json", True)
    kw.setdefault("user_id", None)
    return argparse.Namespace(**kw)


def run(fn, args: argparse.Namespace) -> tuple[str, int | None]:
    """Run a command, return (stdout, exit code or None)."""
    api.set_json_output(bool(getattr(args, "json", False)))
    out = io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            fn(args)
        except SystemExit as e:
            code = e.code
    api.set_json_output(False)
    return out.getvalue(), code


class TestLookalikeCreate(unittest.TestCase):
    def test_payload_shape(self):
        with mock.patch.object(rt, "_api_call", return_value={"listIds": [99]}) as call:
            out, code = run(rt.cmd_lookalike_create, ns(
                name="Lookalike zákazníci", source_list_id=12, accuracy="high", description="d"))
        self.assertIsNone(code)
        method, payload, uid = call.call_args[0]
        self.assertEqual(method, "retargeting.lookalikes.create")
        self.assertEqual(payload, [[{"name": "Lookalike zákazníci", "accuracy": "high",
                                     "sourceRetargetingList": {"id": 12}, "description": "d"}]])
        self.assertEqual(json.loads(out), {"listIds": [99]})

    def test_description_is_optional(self):
        with mock.patch.object(rt, "_api_call", return_value={"listIds": [1]}) as call:
            run(rt.cmd_lookalike_create, ns(name="x", source_list_id=3, accuracy="medium", description=None))
        self.assertNotIn("description", call.call_args[0][1][0][0])


ROWS = [
    {"itemId": "A", "feedItem": "Produkt A", "clicks": 50, "totalMoney": 500.0, "conversions": 2,
     "conversionValue": 3000.0, "pno": 0.1667},
    {"itemId": "B", "feedItem": "Produkt B", "clicks": 80, "totalMoney": 900.0, "conversions": 0,
     "conversionValue": 0.0, "pno": None},
    {"itemId": "C", "feedItem": "Produkt C", "clicks": 5, "totalMoney": 20.0, "conversions": 0,
     "conversionValue": 0.0, "pno": None},
    {"itemId": None, "feedItem": None, "clicks": 3, "totalMoney": 30.0, "conversions": 0,
     "conversionValue": 0.0},
]


def item_stats(**kw: object) -> dict:
    args = ns(premise_id=111, date_from="2026-10-01", date_to="2026-10-31", sort="cost", limit=30,
              only_converting=False, no_conversion_cost=None, **kw)
    with mock.patch.object(nakupy.fenix, "resolve_premise", return_value=111) as rp, \
            mock.patch.object(nakupy.fenix, "call", return_value={"id": 5}) as call, \
            mock.patch.object(nakupy.fenix, "poll_report", return_value={"stats": ROWS}) as poll:
        out, code = run(nakupy.cmd_nakupy_item_stats, args)
    assert code is None, out
    rp.assert_called_once_with(111)
    poll.assert_called_once_with(5)
    return {"out": json.loads(out), "call": call}


class TestItemStats(unittest.TestCase):
    def test_request_goes_to_the_item_endpoint_with_a_local_offset_window(self):
        call = item_stats()["call"]
        method, path, params = call.call_args[0][:3]
        body = call.call_args[1]["body"]
        self.assertEqual((method, path, params), ("POST", "/nakupy/statistics/item", {"premiseId": 111}))
        self.assertEqual(body["format"], ["json"])
        self.assertTrue(body["from"].startswith("2026-10-01T00:00:00"))
        self.assertTrue(body["to"].startswith("2026-10-31T23:59:59"))
        # an explicit UTC offset, as opposed to a bare local time
        self.assertRegex(body["from"], r"[+-]\d\d:\d\d$")

    def test_summary_counts_unassigned_cost_and_pno(self):
        s = item_stats()["out"]["summary"]
        self.assertEqual(s["items"], 3)
        self.assertEqual(s["totalCost"], 1450.0)
        self.assertEqual(s["totalConversionValue"], 3000.0)
        self.assertEqual(s["pno"], round(1450 / 3000, 4))
        self.assertEqual(s["unassignedCost"], 30.0)

    def test_rows_are_sorted_by_cost_and_exclude_the_unassigned_row(self):
        rows = item_stats()["out"]["rows"]
        self.assertEqual([r["itemId"] for r in rows], ["B", "A", "C"])

    def test_no_conversion_cost_keeps_only_wasted_spend(self):
        rows = item_stats(**{})["out"]["rows"]
        self.assertEqual(len(rows), 3)
        args = ns(premise_id=111, date_from="2026-10-01", date_to="2026-10-31", sort="cost", limit=30,
                  only_converting=False, no_conversion_cost=100.0)
        with mock.patch.object(nakupy.fenix, "resolve_premise", return_value=111), \
                mock.patch.object(nakupy.fenix, "call", return_value={"id": 5}), \
                mock.patch.object(nakupy.fenix, "poll_report", return_value={"stats": ROWS}):
            out, _ = run(nakupy.cmd_nakupy_item_stats, args)
        self.assertEqual([r["itemId"] for r in json.loads(out)["rows"]], ["B"])

    def test_only_converting_and_limit(self):
        args = ns(premise_id=111, date_from="2026-10-01", date_to="2026-10-31", sort="clicks", limit=1,
                  only_converting=True, no_conversion_cost=None)
        with mock.patch.object(nakupy.fenix, "resolve_premise", return_value=111), \
                mock.patch.object(nakupy.fenix, "call", return_value={"id": 5}), \
                mock.patch.object(nakupy.fenix, "poll_report", return_value={"stats": ROWS}):
            out, _ = run(nakupy.cmd_nakupy_item_stats, args)
        self.assertEqual([r["itemId"] for r in json.loads(out)["rows"]], ["A"])

    def test_missing_report_id_fails(self):
        args = ns(premise_id=111, date_from="2026-10-01", date_to="2026-10-31", sort="cost", limit=30,
                  only_converting=False, no_conversion_cost=None)
        with mock.patch.object(nakupy.fenix, "resolve_premise", return_value=111), \
                mock.patch.object(nakupy.fenix, "call", return_value={}), \
                mock.patch.object(nakupy.fenix, "poll_report") as poll:
            _, code = run(nakupy.cmd_nakupy_item_stats, args)
        self.assertIsNotNone(code)
        poll.assert_not_called()


if __name__ == "__main__":
    unittest.main()
