"""Offline tests for the retargeting combination commands (`retargeting-combination*`).

No network: `_api_call` / `_fetch_all` are patched. Run from the project root:

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
from sklik.commands import retargeting as rt  # noqa: E402


def ns(**kw: object) -> argparse.Namespace:
    kw.setdefault("json", True)
    kw.setdefault("user_id", None)
    return argparse.Namespace(**kw)


def combo_ns(**kw: object) -> argparse.Namespace:
    kw.setdefault("op_and", None)
    kw.setdefault("op_or", None)
    kw.setdefault("op_not", None)
    kw.setdefault("groups_json", None)
    kw.setdefault("description", None)
    return ns(**kw)


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


class TestCombinationGroups(unittest.TestCase):
    def test_each_flag_occurrence_is_one_group(self):
        groups = rt._combination_groups(combo_ns(op_or=["1,2", "3"], op_not=["4"]))
        self.assertEqual(groups, [{"operator": "or", "listIds": [1, 2]},
                                  {"operator": "or", "listIds": [3]},
                                  {"operator": "not", "listIds": [4]}])

    def test_only_not_is_rejected_before_any_request(self):
        _, code = run(lambda a: rt._combination_groups(a), combo_ns(op_not=["4"]))
        self.assertIsNotNone(code)

    def test_no_groups_and_bad_ids_fail(self):
        for kw in ({}, {"op_and": ["1,x"]}, {"op_or": [" , "]}):
            with self.subTest(kw=kw):
                _, code = run(lambda a: rt._combination_groups(a), combo_ns(**kw))
                self.assertIsNotNone(code)

    def test_groups_json_and_flags_are_exclusive(self):
        _, code = run(lambda a: rt._combination_groups(a),
                      combo_ns(op_and=["1"], groups_json='[{"operator":"or","listIds":[1]}]'))
        self.assertIsNotNone(code)

    def test_groups_json_needs_a_valid_operator(self):
        _, code = run(lambda a: rt._combination_groups(a),
                      combo_ns(groups_json='[{"operator":"xor","listIds":[1]}]'))
        self.assertIsNotNone(code)


class TestCombinationCommands(unittest.TestCase):
    def test_create_sends_attributes_and_list_groups(self):
        with mock.patch.object(rt, "_api_call", return_value={"combinationIds": [55]}) as call:
            out, code = run(rt.cmd_retargeting_combination_create, combo_ns(
                name="Návštěvníci 4–7 d", op_and=["10"], op_not=["11"]))
        self.assertIsNone(code)
        method, payload, uid = call.call_args[0]
        self.assertEqual(method, "retargeting.combinations.create")
        self.assertEqual(payload, [[{"attributes": {"name": "Návštěvníci 4–7 d"},
                                     "listGroups": [{"operator": "and", "listIds": [10]},
                                                    {"operator": "not", "listIds": [11]}]}]])
        self.assertEqual(json.loads(out)["combinationIds"], [55])

    def test_update_sends_attributes_only(self):
        with mock.patch.object(rt, "_api_call", return_value={}) as call:
            run(rt.cmd_retargeting_combination_update, ns(
                combination_id=5, name=None, description="d", status="suspend"))
        self.assertEqual(call.call_args[0][:2], (
            "retargeting.combinations.update",
            [[{"combinationId": 5, "attributes": {"description": "d", "status": "suspend"}}]]))

    def test_update_without_fields_fails(self):
        with mock.patch.object(rt, "_api_call") as call:
            _, code = run(rt.cmd_retargeting_combination_update, ns(
                combination_id=5, name=None, description=None, status=None))
        self.assertIsNotNone(code)
        call.assert_not_called()

    def test_remove_and_detach_need_confirm(self):
        with mock.patch.object(rt, "_api_call") as call:
            _, c1 = run(rt.cmd_retargeting_combination_remove, ns(combination_id=5, confirm=False))
            _, c2 = run(rt.cmd_retargeting_combination_detach,
                        ns(combination_id=5, group_id=9, confirm=False))
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        call.assert_not_called()

    def test_attach_and_detach_payloads(self):
        with mock.patch.object(rt, "_api_call", return_value={"count": 1}) as call:
            run(rt.cmd_retargeting_combination_attach, ns(combination_id=5, group_id=9))
            self.assertEqual(call.call_args[0][:2], (
                "retargeting.group.combinations.add", [[{"combinationId": 5, "groupId": 9}]]))
            run(rt.cmd_retargeting_combination_detach, ns(combination_id=5, group_id=9, confirm=True))
            self.assertEqual(call.call_args[0][:2], (
                "retargeting.group.combinations.remove", [[{"combinationId": 5, "groupId": 9}]]))

    def test_list_hides_deleted_and_detail_joins_groups(self):
        def fake(method, params, uid=None, **kw):
            if method == "retargeting.combinations.list":
                return {"combinations": [
                    {"combinationId": 1, "name": "a", "status": "active", "deleted": False},
                    {"combinationId": 2, "name": "b", "status": "active", "deleted": True}]}
            self.assertEqual(method, "retargeting.combinations.get")
            self.assertEqual(params, [[1]])
            return {"combinations": [{"combinationId": 1, "attributes": {"users": 42},
                                      "listGroups": [{"operator": "or", "listIds": [7, 8]}]}]}
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            out, _ = run(rt.cmd_retargeting_combinations, ns(detail=True, include_deleted=False))
        rows = json.loads(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["users"], 42)
        self.assertEqual(rows[0]["listGroups"], [{"operator": "or", "listIds": [7, 8]}])


class TestAttachedListingsAreChunked(unittest.TestCase):
    def test_attached_combinations_ask_per_chunk_and_skip_deleted(self):
        calls = []

        def fake(method, params, uid=None, **kw):
            calls.append((method, params))
            return {"combinations": [{"combinationId": 1, "groupId": params[0][0], "name": "a",
                                      "status": "active", "deleted": False},
                                     {"combinationId": 2, "groupId": params[0][0], "deleted": True}]}
        groups = [{"id": i} for i in range(1, 6)]
        with mock.patch.object(rt, "_api_call", side_effect=fake), \
                mock.patch.object(rt, "_fetch_all", return_value=groups), \
                mock.patch.object(rt, "_list_page_size", return_value=2):
            out, _ = run(rt.cmd_retargeting_combinations_attached, ns(group_id=None))
        self.assertEqual([p[0] for _, p in calls], [[1, 2], [3, 4], [5]])
        self.assertEqual([r["groupId"] for r in json.loads(out)], [1, 3, 5])

    def test_attached_lists_still_work_after_the_refactor(self):
        with mock.patch.object(rt, "_api_call", return_value={"lists": [
                {"listId": 3, "groupId": 9, "name": "l", "status": "active", "deleted": False},
                {"listId": 4, "groupId": 9, "deleted": True}]}) as call:
            out, _ = run(rt.cmd_retargeting_attached, ns(group_id=9))
        self.assertEqual(call.call_args[0][:2], ("retargeting.group.lists.list", [[9]]))
        self.assertEqual([r["listId"] for r in json.loads(out)], [3])


if __name__ == "__main__":
    unittest.main()
