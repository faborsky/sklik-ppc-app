"""Offline tests for the campaign-type lookup of `fenix-campaign-update`.

The PATCH body needs the campaign's `type`; without `--type` the CLI reads it
from the listing. Live 2026-11-27: a single `ids=<id>` is a 422, `id=<id>`
filters to the campaign. No network: `fenix.call` is patched.

    source venv/bin/activate && python -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sklik.api as api  # noqa: E402
from sklik.commands import fenix_sklik  # noqa: E402


class CampaignTypeLookup(unittest.TestCase):

    def test_sends_the_id_filter_not_a_single_ids(self):
        with mock.patch.object(fenix_sklik.fenix, "call",
                               return_value={"items": [{"id": 42, "type": "context"}]}) as call:
            self.assertEqual(fenix_sklik._campaign_type(42), "context")
        method, path, params = call.call_args.args[:3]
        self.assertEqual((method, path), ("GET", "/sklik/campaigns/"))
        self.assertEqual(params.get("id"), 42)
        self.assertNotIn("ids", params)
        self.assertEqual(params.get("a"), ["id", "type"])

    def test_ignores_other_campaigns_in_the_answer(self):
        items = [{"id": 7, "type": "fulltext"}, {"id": 42, "type": "product"}]
        with mock.patch.object(fenix_sklik.fenix, "call", return_value={"items": items}):
            self.assertEqual(fenix_sklik._campaign_type(42), "product")

    def test_unknown_campaign_fails_cleanly(self):
        api.set_json_output(True)
        out = io.StringIO()
        with mock.patch.object(fenix_sklik.fenix, "call", return_value={"items": []}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                fenix_sklik._campaign_type(999)
        self.assertIn("999", out.getvalue())


if __name__ == "__main__":
    unittest.main()
