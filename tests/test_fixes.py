"""Offline tests for the request shapes and error paths of v1.12.0.

No network: every API entry point is patched. Run from the project root:

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
import sklik.fenix as fenix  # noqa: E402
from sklik.commands import keywords, nakupy, research, sitelinks, campaigns  # noqa: E402


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


class FakeResp:
    def __init__(self, status: int, body: object = None, text: str = "", headers=None):
        self.status_code = status
        self._body = body
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


# ---------------------------------------------------------------------------
# #7 — HTTP 429 without a JSON body, suggest-stats > 100 queries
# ---------------------------------------------------------------------------

class TestDrak429(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.object(api, "_current_session", "sess"),
            mock.patch.object(api, "_throttle_request"),
            mock.patch.object(api, "_record_request"),
            mock.patch.object(api, "_save_session"),
            mock.patch("time.sleep"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        mock.patch.stopall()

    def test_bodyless_429_is_retried_not_non_json_error(self):
        responses = [FakeResp(429, None, "Too Many Requests"),
                     FakeResp(200, {"status": 200, "campaigns": []})]
        with mock.patch("requests.post", side_effect=responses) as post:
            data = api._api_call("campaigns.list", [{}])
        self.assertEqual(data["status"], 200)
        self.assertEqual(post.call_count, 2)

    def test_429_with_json_body_still_works(self):
        responses = [FakeResp(429, {"status": 429, "statusMessage": "wait"}),
                     FakeResp(200, {"status": 200})]
        with mock.patch("requests.post", side_effect=responses) as post:
            api._api_call("campaigns.list", [{}])
        self.assertEqual(post.call_count, 2)

    def test_429_gives_up_after_three_retries(self):
        with mock.patch("requests.post", return_value=FakeResp(429)) as post, \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            api._api_call("campaigns.list", [{}])
        self.assertEqual(post.call_count, 4)

    def test_other_non_json_still_fails(self):
        with mock.patch("requests.post", return_value=FakeResp(502, None, "<html>")), \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            api._api_call("campaigns.list", [{}])


class TestSuggestStatsChunks(unittest.TestCase):
    def test_250_queries_go_in_chunks_of_100(self):
        queries = [f"dotaz {i}" for i in range(250)]

        def fake(method, params, *a, **k):
            return {"stats": [{"query": q, "avgSearchCount": 1, "avgCpc": 100}
                              for q in params[0]]}

        with mock.patch.object(research, "_api_call", side_effect=fake) as call:
            out, code = run(research.cmd_suggest_stats,
                            ns(queries=",".join(queries) + ", ,", granularity="monthly"))
        self.assertIsNone(code)
        self.assertEqual([len(c.args[1][0]) for c in call.call_args_list], [100, 100, 50])
        rows = json.loads(out)
        self.assertEqual(len(rows), 250)
        self.assertEqual(rows[0]["avgCpc"], 1.0)


# ---------------------------------------------------------------------------
# #3 — negative-remove after DRAK 11.27.0
# ---------------------------------------------------------------------------

class TestNegativeRemove(unittest.TestCase):
    def test_by_name_sends_group_id_and_name_match(self):
        with mock.patch.object(keywords, "_api_call", return_value={"status": 200}) as call:
            out, code = run(keywords.cmd_negative_remove,
                            ns(group_id=7, name="zdarma", match_type="negativePhrase",
                               keyword_id=None, confirm=True))
        self.assertIsNone(code)
        call.assert_called_once_with(
            "keywords.negative.remove",
            [7, [{"name": "zdarma", "matchType": "negativePhrase"}]], None)
        self.assertTrue(json.loads(out)["removed"])

    def test_short_match_type_is_normalised(self):
        with mock.patch.object(keywords, "_api_call", return_value={}) as call:
            run(keywords.cmd_negative_remove,
                ns(group_id=7, name="x", match_type="exact", keyword_id=None, confirm=True))
        self.assertEqual(call.call_args.args[1][1][0]["matchType"], "negativeExact")

    def test_by_keyword_id_looks_up_then_deletes_by_name(self):
        listing = {"keywords": [{"id": 55, "name": "levně", "matchType": "phrase",
                                 "group": {"id": 9}}]}
        with mock.patch.object(keywords, "_api_call",
                               side_effect=[listing, {"status": 200}]) as call:
            out, code = run(keywords.cmd_negative_remove,
                            ns(group_id=None, name=None, match_type="negativeBroad",
                               keyword_id=55, confirm=True))
        self.assertIsNone(code)
        lookup, remove = call.call_args_list
        self.assertEqual(lookup.args[0], "keywords.negative.list")
        self.assertEqual(lookup.args[1][0], {"ids": [55]})
        self.assertEqual(remove.args[1], [9, [{"name": "levně",
                                               "matchType": "negativePhrase"}]])

    def test_unknown_keyword_id_fails_without_delete(self):
        with mock.patch.object(keywords, "_api_call", return_value={"keywords": []}) as call:
            out, code = run(keywords.cmd_negative_remove,
                            ns(group_id=None, name=None, match_type="negativeBroad",
                               keyword_id=55, confirm=True))
        self.assertEqual(code, 1)
        self.assertEqual(call.call_count, 1)
        self.assertIn("not found", json.loads(out)["error"]["message"])

    def test_requires_confirm_and_target(self):
        with mock.patch.object(keywords, "_api_call") as call:
            _, c1 = run(keywords.cmd_negative_remove,
                        ns(group_id=7, name="x", match_type="negativeBroad",
                           keyword_id=None, confirm=False))
            _, c2 = run(keywords.cmd_negative_remove,
                        ns(group_id=None, name="x", match_type="negativeBroad",
                           keyword_id=None, confirm=True))
        self.assertEqual((c1, c2), (1, 1))
        call.assert_not_called()

    def test_negative_add_reports_without_ids(self):
        with mock.patch.object(keywords, "_api_call", return_value={"status": 200}):
            out, _ = run(keywords.cmd_negative_add_batch,
                         ns(group_id=7, campaign_id=None,
                            keywords_json='["a", {"name": "b", "matchType": "negativeExact"}]'))
        self.assertEqual(json.loads(out)["added"], 2)


# ---------------------------------------------------------------------------
# #6 — feed URL secrets
# ---------------------------------------------------------------------------

class TestFeedUrlMask(unittest.TestCase):
    CASES = {
        "https://e.cz/export/products.xml?hash=abc123": "https://e.cz/export/products.xml?hash=***",
        "https://e.cz/f.xml?lang=cs&feed_token=XYZ&x=1": "https://e.cz/f.xml?lang=cs&feed_token=***&x=1",
        "https://e.cz/f.xml?KEY=1&Password=2": "https://e.cz/f.xml?KEY=***&Password=***",
        "https://user:pw@e.cz/f.xml": "https://***@e.cz/f.xml",
        "https://e.cz/f.xml?keyword=boty&monkey=1": "https://e.cz/f.xml?keyword=boty&monkey=1",
        "https://e.cz/f.xml": "https://e.cz/f.xml",
    }

    def test_mask(self):
        for raw, masked in self.CASES.items():
            self.assertEqual(nakupy._mask_feed_url(raw), masked, raw)
        self.assertIsNone(nakupy._mask_feed_url(None))

    def test_feed_status_json_and_text_are_masked(self):
        feeds = {"items": [{"id": 1, "feedUrl": "https://e.cz/f.xml?hash=SECRET",
                            "maxFeedDownloadsPerDay": None}]}
        with mock.patch.object(fenix, "resolve_premise", return_value=1), \
                mock.patch.object(fenix, "call", return_value=feeds):
            out_json, _ = run(nakupy.cmd_feed_status, ns(premise_id=None, json=True))
            out_text, _ = run(nakupy.cmd_feed_status, ns(premise_id=None, json=False))
        self.assertNotIn("SECRET", out_json + out_text)
        self.assertEqual(json.loads(out_json)[0]["feedUrl"], "https://e.cz/f.xml?hash=***")


# ---------------------------------------------------------------------------
# Callouts ↔ sitelinks share one assignment set
# ---------------------------------------------------------------------------

ASSIGNED = {"campaigns": [{"id": 3, "sitelinks": [
    {"id": 10, "name": "Kontakt", "url": "https://e.cz/k"},
    {"id": 20, "name": "Doprava zdarma", "url": None},
]}]}


class TestAssignKeepsTheOtherKind(unittest.TestCase):
    def test_sitelink_assign_keeps_callouts(self):
        with mock.patch.object(sitelinks, "_api_call",
                               side_effect=[ASSIGNED, {"status": 200}]) as call:
            out, code = run(sitelinks.cmd_sitelink_assign,
                            ns(campaign_id=3, group_id=None, sitelink_ids="11,12"))
        self.assertIsNone(code)
        self.assertEqual(call.call_args_list[1].args,
                         ("sitelinks.campaign.set", [[{"id": 3, "sitelinkIds": [11, 12, 20]}]], None))
        self.assertEqual(json.loads(out)["keptCallouts"], [20])

    def test_sitelink_assign_empty_clears_only_sitelinks(self):
        with mock.patch.object(sitelinks, "_api_call",
                               side_effect=[ASSIGNED, {"status": 200}]) as call:
            run(sitelinks.cmd_sitelink_assign, ns(campaign_id=3, group_id=None, sitelink_ids=""))
        self.assertEqual(call.call_args_list[1].args[1][0][0]["sitelinkIds"], [20])

    def test_callout_assign_keeps_sitelinks(self):
        records = {"sitelinks": [{"id": 20, "url": None}, {"id": 21, "url": None},
                                 {"id": 10, "url": "https://e.cz/k"}]}
        with mock.patch.object(sitelinks, "_api_call",
                               side_effect=[records, ASSIGNED, {"status": 200}]) as call:
            run(sitelinks.cmd_callout_assign,
                ns(campaign_id=3, group_id=None, callout_ids="21", dry_run=False))
        self.assertEqual(call.call_args_list[2].args[1][0][0]["sitelinkIds"], [10, 21])


# ---------------------------------------------------------------------------
# Fénix engine (PR #2) and DRAK campaign dates (PR #9)
# ---------------------------------------------------------------------------

class TestFenixEngine(unittest.TestCase):
    def test_retry_after_forms(self):
        self.assertEqual(fenix._retry_after(FakeResp(429, headers={"Retry-After": "7"})), 7.0)
        self.assertIsNone(fenix._retry_after(FakeResp(429)))
        self.assertIsNone(fenix._retry_after(FakeResp(429, headers={"Retry-After": "soon"})))

    def test_204_is_success(self):
        with mock.patch.object(fenix, "_request", return_value=FakeResp(204)):
            self.assertEqual(fenix.call("POST", "/x"), {})


class TestCampaignDates(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(campaigns._parse_date("2026-12-31", "--end-date", False), "2026-12-31")
        self.assertIsNone(campaigns._parse_date("none", "--end-date", True))
        self.assertIs(campaigns._parse_date(None, "--end-date", True), campaigns._DATE_UNSET)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            campaigns._parse_date("31.12.2026", "--end-date", True)


if __name__ == "__main__":
    unittest.main()
