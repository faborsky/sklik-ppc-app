"""Offline tests for the e-mail audience commands (`retargeting-email*`).

No network: `_api_call` is patched. Run from the project root:

    source venv/bin/activate && python -m unittest discover -s tests -v
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sklik.api as api  # noqa: E402
from sklik.commands import retargeting as rt  # noqa: E402


def ns(**kw: object) -> argparse.Namespace:
    kw.setdefault("json", True)
    kw.setdefault("user_id", None)
    kw.setdefault("emails", None)
    kw.setdefault("file", None)
    return argparse.Namespace(**kw)


def run(fn, args: argparse.Namespace) -> tuple[str, str, int | None]:
    """Run a command, return (stdout, stderr, exit code or None)."""
    api.set_json_output(bool(getattr(args, "json", False)))
    out, err = io.StringIO(), io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            fn(args)
        except SystemExit as e:
            code = e.code
    api.set_json_output(False)
    return out.getvalue(), err.getvalue(), code


def terms(accepted: bool | None = True):
    """_api_call stand-in: the terms check answers `accepted`, everything else is recorded."""
    calls: list[tuple[str, object]] = []

    def fake(method, params=None, uid=None, **kw):
        calls.append((method, params))
        if method == "retargeting.email.contractCondition.check":
            return {"contractAccepted": accepted}
        return {}
    return fake, calls


class TestReadEmails(unittest.TestCase):
    def test_trims_lowercases_deduplicates_and_counts_rejects(self):
        emails, rejected = rt._read_emails(ns(emails=" A@B.cz ,a@b.CZ,c@d.cz,not-an-address,x y@z.cz,,"))
        self.assertEqual(emails, ["a@b.cz", "c@d.cz"])
        self.assertEqual(rejected, 2)

    def test_file_takes_first_column_of_csv_and_skips_header_and_bom(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as fh:
            fh.write('e-mail;name\n"A@b.cz";Jan\nc@d.cz,Eva\nA@B.cz\n')
            path = fh.name
        try:
            emails, rejected = rt._read_emails(ns(file=path))
        finally:
            os.unlink(path)
        self.assertEqual(emails, ["a@b.cz", "c@d.cz"])
        self.assertEqual(rejected, 1)  # the header row

    def test_emails_and_file_are_combined(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write("f@g.cz\n")
            path = fh.name
        try:
            emails, _ = rt._read_emails(ns(emails="a@b.cz", file=path))
        finally:
            os.unlink(path)
        self.assertEqual(emails, ["a@b.cz", "f@g.cz"])

    def test_no_input_and_no_valid_address_fail(self):
        for kw in ({}, {"emails": "nope,also-nope"}, {"file": "does-not-exist.csv"}):
            with self.subTest(kw=kw):
                _, _, code = run(lambda a: rt._read_emails(a), ns(**kw))
                self.assertIsNotNone(code)


class TestEmailWrites(unittest.TestCase):
    def test_add_sends_batches_of_1000_with_the_list_id(self):
        fake, calls = terms()
        emails = ",".join(f"user{i}@firma.cz" for i in range(2500))
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            out, _, code = run(rt.cmd_retargeting_email_add, ns(list_id=7, emails=emails))
        self.assertIsNone(code)
        sends = [(m, p) for m, p in calls if m == "retargeting.emails.addEmail"]
        self.assertEqual([len(p[0]["emails"]) for _, p in sends], [1000, 1000, 500])
        self.assertTrue(all(p[0]["retargetingListId"] == 7 for _, p in sends))
        self.assertEqual(json.loads(out), {"listId": 7, "sent": 2500, "rejected": 0})

    def test_addresses_are_never_printed(self):
        fake, _ = terms()
        for as_json in (True, False):
            with self.subTest(json=as_json), mock.patch.object(rt, "_api_call", side_effect=fake):
                out, err, _ = run(rt.cmd_retargeting_email_add,
                                  ns(list_id=7, emails="secret.person@firma.cz,bad", json=as_json))
            self.assertNotIn("secret.person", out + err)
            self.assertNotIn("@", out + err)

    def test_writes_stop_before_sending_when_terms_are_not_accepted(self):
        fake, calls = terms(accepted=False)
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            _, _, c1 = run(rt.cmd_retargeting_email_add, ns(list_id=7, emails="a@b.cz"))
            _, _, c2 = run(rt.cmd_retargeting_email_create, ns(name="x", description=None))
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        self.assertEqual({m for m, _ in calls}, {"retargeting.email.contractCondition.check"})

    def test_remove_emails_and_clear_need_confirm(self):
        fake, calls = terms()
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            _, _, c1 = run(rt.cmd_retargeting_email_remove_emails,
                           ns(list_id=7, emails="a@b.cz", confirm=False))
            _, _, c2 = run(rt.cmd_retargeting_email_clear, ns(list_id=7, confirm=False))
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        self.assertEqual(calls, [])

    def test_remove_emails_and_clear_payloads(self):
        fake, calls = terms()
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            run(rt.cmd_retargeting_email_remove_emails, ns(list_id=7, emails="A@b.cz", confirm=True))
            run(rt.cmd_retargeting_email_clear, ns(list_id=7, confirm=True))
        self.assertIn(("retargeting.emails.removeEmail",
                       [{"retargetingListId": 7, "emails": ["a@b.cz"]}]), calls)
        self.assertIn(("retargeting.emails.removeAll", [{"retargetingListId": 7}]), calls)

    def test_create_uses_flat_items_not_attributes(self):
        fake, calls = terms()
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            run(rt.cmd_retargeting_email_create, ns(name="VIP zákazníci", description="nad 5 000 Kč"))
        self.assertIn(("retargeting.emails.create",
                       [[{"name": "VIP zákazníci", "description": "nad 5 000 Kč"}]]), calls)

    def test_update_uses_retargeting_list_id_and_needs_a_field(self):
        fake, calls = terms()
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            run(rt.cmd_retargeting_email_update,
                ns(list_id=7, name=None, description=None, status="suspend"))
            _, _, code = run(rt.cmd_retargeting_email_update,
                             ns(list_id=7, name=None, description=None, status=None))
        self.assertIn(("retargeting.emails.update",
                       [[{"retargetingListId": 7, "status": "suspend"}]]), calls)
        self.assertIsNotNone(code)


class TestEmailReads(unittest.TestCase):
    def test_terms_command_reports_the_flag(self):
        fake, _ = terms(accepted=False)
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            out, _, _ = run(rt.cmd_retargeting_email_terms, ns())
        self.assertEqual(json.loads(out), {"contractAccepted": False})

    def test_list_uses_email_id_hides_deleted_and_joins_counts(self):
        def fake(method, params=None, uid=None, **kw):
            if method == "retargeting.emails.list":
                return {"emails": [{"emailId": 1, "name": "a", "status": "active", "deleted": False},
                                   {"emailId": 2, "name": "b", "status": "active", "deleted": True}]}
            self.assertEqual((method, params), ("retargeting.emails.get", [[1]]))
            return {"emails": [{"emailId": 1, "attributes": {"users": 120, "membership": 90}}]}
        with mock.patch.object(rt, "_api_call", side_effect=fake):
            out, _, _ = run(rt.cmd_retargeting_emails, ns(detail=True, include_deleted=False))
        rows = json.loads(out)
        self.assertEqual(rows, [{"listId": 1, "name": "a", "status": "active", "deleted": False,
                                 "users": 120, "membership": 90}])


if __name__ == "__main__":
    unittest.main()
