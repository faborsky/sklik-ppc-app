"""Offline tests for the 2026-11 fixes: negative-keyword networks,
per-group stats paging, placement-stats, ad read-back, detailCpc.

No network: every API entry point is patched. Run from the project root:

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sklik.reports as reports  # noqa: E402
from sklik.commands import ads, fenix_sklik, keywords, placements  # noqa: E402
from test_fixes import ns, run  # noqa: E402


# ---------------------------------------------------------------------------
# Negative keywords — network (Fénix 1.40.0)
# ---------------------------------------------------------------------------

class TestFenixNegativeNetwork(unittest.TestCase):
    def test_fenix_negative_add_passes_network(self):
        args = ns(campaign_id=7, group_id=None, name="x", match_type="negativeBroad",
                  network="context", dry_run=False)
        with mock.patch.object(fenix_sklik.fenix, "call", return_value=None) as call:
            run(fenix_sklik.cmd_fenix_negative_add, args)
        body = call.call_args.kwargs["body"]
        self.assertEqual(body["network"], "context")
        self.assertEqual(body["negativeKeywords"][0]["matchType"], "negative")


# ---------------------------------------------------------------------------
# Report paging: the 5000 cap counts entities × periods
# ---------------------------------------------------------------------------

class TestPeriodPaging(unittest.TestCase):
    def test_period_count(self):
        self.assertEqual(reports._period_count("2026-10-20", "2026-11-17", "total"), 1)
        self.assertEqual(reports._period_count("2026-10-20", "2026-11-17", "daily"), 29)
        self.assertEqual(reports._period_count("2026-10-20", "2026-11-17", "monthly"), 2)
        self.assertGreaterEqual(reports._period_count("2026-10-20", "2026-11-17", "weekly"), 5)

    def test_daily_report_pages_stay_under_the_cap(self):
        limits = []

        def fake(method, params, uid=None, **kw):
            if method.endswith("createReport"):
                return {"reportId": "r", "totalCount": 15000}
            limits.append(params[1]["limit"])
            return {"report": []}

        with mock.patch.object(reports, "_api_call", side_effect=fake), \
                mock.patch.object(reports, "_list_page_size", return_value=5000):
            reports._fetch_report("keywords", {}, "2026-10-20", "2026-11-17",
                                  ["id"], granularity="daily")
        self.assertTrue(limits)
        self.assertTrue(all(lim * 29 <= 5000 for lim in limits))
        self.assertEqual(sum(limits), 15000)


class TestGroupStatsRestriction(unittest.TestCase):
    def _args(self, **kw):
        base = dict(group_id=5, campaign_id=None, date_from="2026-11-01",
                    date_to="2026-11-07", granularity="daily")
        base.update(kw)
        return ns(**base)

    def test_keyword_stats_sends_group_ids(self):
        with mock.patch.object(keywords, "_group_entity_ids", return_value=[11, 12]), \
                mock.patch.object(keywords, "_fetch_report", return_value=[]) as rep:
            run(keywords.cmd_keyword_stats, self._args())
        self.assertEqual(rep.call_args.args[1], {"ids": [11, 12]})

    def test_empty_group_does_not_report_whole_account(self):
        with mock.patch.object(ads, "_group_entity_ids", return_value=[]), \
                mock.patch.object(ads, "_fetch_report") as rep:
            out, _ = run(ads.cmd_ad_stats, self._args())
        rep.assert_not_called()
        self.assertEqual(json.loads(out), [])

    def test_group_entity_ids_filters_by_group(self):
        rows = [{"id": 1, "group": {"id": 5}}, {"id": 2, "group": {"id": 6}},
                {"id": 3, "group.id": 5}]
        with mock.patch("sklik.api._fetch_all", return_value=rows):
            self.assertEqual(reports._group_entity_ids("keywords.list", "keywords", 5, None),
                             [1, 3])


# ---------------------------------------------------------------------------
# placement-stats
# ---------------------------------------------------------------------------

class TestPlacementStats(unittest.TestCase):
    def test_columns_and_filter(self):
        rows = [{"id": 1, "pattern": "a.cz", "cpc": 300, "group": {"id": 5},
                 "campaign": {"id": 9}, "stats": [{"clicks": 2, "totalMoney": 1000}]},
                {"id": 2, "pattern": "b.cz", "group": {"id": 6}, "campaign": {"id": 9},
                 "stats": []}]
        args = ns(group_id=5, campaign_id=None, date_from=None, date_to=None,
                  granularity="total")
        with mock.patch.object(placements, "_fetch_report", return_value=rows) as rep:
            out, code = run(placements.cmd_placement_stats, args)
        self.assertIsNone(code)
        cols = rep.call_args.args[4]
        self.assertNotIn("ishContext", cols)
        self.assertIn("conversions", cols)
        res = json.loads(out)
        self.assertEqual([r["id"] for r in res], [1])
        self.assertEqual(res[0]["cpc"], 3)


# ---------------------------------------------------------------------------
# ad-replace / ad-create read-back
# ---------------------------------------------------------------------------

AD = {"id": 100, "adType": "eta", "headline1": "A", "headline2": "B",
      "description": "D", "finalUrl": "https://x.cz", "group": {"id": 5}}


class TestAdReadBack(unittest.TestCase):
    def _replace_args(self, **kw):
        base = dict(ad_id=100, headline1="Nový", headline2=None, headline3=None,
                    description1=None, description2=None, final_url=None,
                    path1=None, path2=None)
        base.update(kw)
        return ns(**base)

    def _fake(self, update_result, live):
        def fake(method, params, uid=None, **kw):
            if method == "ads.list":
                cols = params[1]["displayColumns"]
                return {"ads": [live if "adType" not in cols else AD]}
            if method == "ads.check":
                return {"status": 200}
            if method == "ads.update":
                return update_result
            raise AssertionError(method)
        return fake

    def test_in_place_update_is_reported(self):
        live = dict(AD, headline1="Nový")
        with mock.patch.object(ads, "_api_call", side_effect=self._fake({}, live)):
            out, _ = run(ads.cmd_ad_replace, self._replace_args())
        res = json.loads(out)
        self.assertTrue(res["updatedInPlace"])
        self.assertEqual(res["adId"], 100)
        self.assertNotIn("droppedFields", res)

    def test_dropped_headline3_is_flagged(self):
        live = dict(AD, id=200)
        fake = self._fake({"newAdIds": [200]}, live)
        with mock.patch.object(ads, "_api_call", side_effect=fake):
            out, _ = run(ads.cmd_ad_replace, self._replace_args(headline1="A", headline3="Tři"))
        res = json.loads(out)
        self.assertFalse(res["updatedInPlace"])
        self.assertEqual(res["droppedFields"], ["headline3"])

    def test_ad_create_flags_dropped_description2(self):
        def fake(method, params, uid=None, **kw):
            if method == "ads.create":
                return {"adIds": [300]}
            return {"ads": [dict(AD, id=300)]}
        args = ns(group_id=5, headline1="A", headline2="B", headline3=None,
                  description1="D", description2="Druhý", final_url="https://x.cz",
                  path1=None, path2=None)
        with mock.patch.object(ads, "_api_call", side_effect=fake):
            out, _ = run(ads.cmd_ad_create, args)
        self.assertEqual(json.loads(out)["droppedFields"], ["description2"])


class TestDetailCpcName(unittest.TestCase):
    def test_no_cpc_to_win_label(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "sklik", "commands", "nakupy.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("cpcToWin", src)
        self.assertIn("detailCpc=", src)


if __name__ == "__main__":
    unittest.main()
