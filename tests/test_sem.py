"""Offline tests for the SEM commands (`sem-*`, Fénix API).

No network: `fenix.call` / `fenix.fetch_all_offset` are patched. Run from the project root:

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
from sklik.commands import sem  # noqa: E402


def ns(**kw: object) -> argparse.Namespace:
    kw.setdefault("json", True)
    kw.setdefault("user_id", None)
    kw.setdefault("condition", None)
    kw.setdefault("conditions_json", None)
    kw.setdefault("dry_run", False)
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


class TestCondition(unittest.TestCase):
    def test_value_condition_is_converted_from_czk_to_halere(self):
        self.assertEqual(sem._parse_condition("value:greater_than:1500"),
                         {"key": "value", "type": "greater_than", "value": "150000"})

    def test_decimal_comma_in_value(self):
        self.assertEqual(sem._parse_condition("value:less_than:99,5")["value"], "9950")

    def test_other_keys_are_passed_through(self):
        self.assertEqual(sem._parse_condition("url:contains:/dekujeme"),
                         {"key": "url", "type": "contains", "value": "/dekujeme"})

    def test_value_may_contain_colons(self):
        self.assertEqual(sem._parse_condition("url:starts:https://shop.cz/a")["value"],
                         "https://shop.cz/a")

    def test_bad_specs_fail(self):
        for spec in ("value:greater_than", "bogus:equals:1", "url:near:x", "value:greater_than:abc",
                     "url:equals:"):
            with self.subTest(spec=spec), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    sem._parse_condition(spec)

    def test_several_conditions_go_into_one_group(self):
        groups = sem._condition_groups(ns(condition=["value:greater_than:1500", "url:contains:/x"]))
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["conditions"]), 2)

    def test_condition_and_json_are_exclusive(self):
        out, code = run(lambda a: sem._condition_groups(a),
                        ns(condition=["url:contains:/x"], conditions_json="[]"))
        self.assertIsNotNone(code)


class TestSemCommands(unittest.TestCase):
    def test_create_dry_run_sends_dryrun_and_returns_no_ids(self):
        with mock.patch.object(sem.fenix, "call", return_value={}) as call:
            out, code = run(sem.cmd_sem_conversion_create, ns(
                name="Nákup nad 1 500 Kč (vedlejší)", event="Purchase", value=0, description=None,
                condition=["value:greater_than:1500"], dry_run=True))
        self.assertIsNone(code)
        method, path, params, body = call.call_args[0]
        self.assertEqual((method, path, params), ("POST", sem._CONVERSIONS, {"dryRun": "true"}))
        self.assertEqual(body["semEventName"], "Purchase")
        self.assertEqual(body["conditionGroups"],
                         [{"conditions": [{"key": "value", "type": "greater_than", "value": "150000"}]}])
        data = json.loads(out)
        self.assertTrue(data["dryRun"])
        self.assertNotIn("conversionIds", data)

    def test_create_returns_conversion_and_list_ids(self):
        with mock.patch.object(sem.fenix, "call",
                               return_value={"conversionIds": [7], "retargetingListIds": [9]}) as call:
            out, _ = run(sem.cmd_sem_conversion_create, ns(
                name="x", event="Lead", value=0, description="d"))
        self.assertIsNone(call.call_args[0][2])
        data = json.loads(out)
        self.assertEqual((data["conversionIds"], data["retargetingListIds"]), ([7], [9]))
        self.assertEqual(call.call_args[0][3]["description"], "d")

    def test_list_pages_through_fetch_all_offset_and_hides_deleted_server_side(self):
        rows = [{"id": 1, "name": "a", "value": 0, "semEventName": "Purchase", "isDeleted": False}]
        with mock.patch.object(sem.fenix, "fetch_all_offset", return_value=rows) as fetch:
            out, _ = run(sem.cmd_sem_conversions, ns(include_deleted=False))
        path, params = fetch.call_args[0]
        self.assertEqual(path, sem._CONVERSIONS)
        self.assertEqual(params["isDeleted"], "false")
        self.assertEqual(params["order"], "id:ASC")
        self.assertEqual(json.loads(out), rows)

    def test_list_with_include_deleted_does_not_filter(self):
        with mock.patch.object(sem.fenix, "fetch_all_offset", return_value=[]) as fetch:
            run(sem.cmd_sem_conversions, ns(include_deleted=True))
        self.assertNotIn("isDeleted", fetch.call_args[0][1])

    def test_update_requires_a_field(self):
        with mock.patch.object(sem.fenix, "call") as call:
            out, code = run(sem.cmd_sem_conversion_update, ns(
                conversion_id=5, name=None, description=None, value=None))
        self.assertIsNotNone(code)
        call.assert_not_called()

    def test_update_dry_run_patches_with_dryrun(self):
        with mock.patch.object(sem.fenix, "call", return_value={}) as call:
            out, code = run(sem.cmd_sem_conversion_update, ns(
                conversion_id=5, name="new", description=None, value=0, dry_run=True))
        self.assertIsNone(code)
        self.assertEqual(call.call_args[0][:3], ("PATCH", f"{sem._CONVERSIONS}5/", {"dryRun": "true"}))
        self.assertEqual(call.call_args[0][3], {"name": "new", "value": 0})
        self.assertEqual(json.loads(out)["updated"], False)

    def test_remove_needs_confirm_and_restore_does_not(self):
        with mock.patch.object(sem.fenix, "call") as call:
            _, code = run(sem.cmd_sem_conversion_remove, ns(conversion_id=5, confirm=False, restore=False))
        self.assertIsNotNone(code)
        call.assert_not_called()

        with mock.patch.object(sem.fenix, "call", return_value={}) as call:
            run(sem.cmd_sem_conversion_remove, ns(conversion_id=5, confirm=True, restore=False))
            self.assertEqual(call.call_args[0][3], {"deleted": True})
            run(sem.cmd_sem_conversion_remove, ns(conversion_id=5, confirm=False, restore=True))
            self.assertEqual(call.call_args[0][3], {"deleted": False})


if __name__ == "__main__":
    unittest.main()
