"""Offline regression tests for complete-day pulse windows and campaign activity."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklik import reports  # noqa: E402
from sklik.commands import account, placements, display_targeting  # noqa: E402


TODAY = datetime(2026, 11, 18, 23, 49)


def ns(**kw: object) -> argparse.Namespace:
    defaults = dict(json=True, account="default", user_id=None, days=7,
                    date_from=None, date_to=None, no_compare=False)
    defaults.update(kw)
    return argparse.Namespace(**defaults)


def row(cid, name, **stats):
    return {"id": cid, "name": name, "stats": [stats]}


class TestPulse(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        clock = stack.enter_context(mock.patch.object(account, "datetime", wraps=datetime))
        clock.now.return_value = TODAY
        clock = stack.enter_context(mock.patch.object(reports, "datetime", wraps=datetime))
        clock.now.return_value = TODAY
        stack.enter_context(mock.patch.object(reports, "_today_stats_warned", False))
        self.api = stack.enter_context(mock.patch.object(account, "_api_call",
                                                       return_value={"status": 200, "days": []}))
        self.fetch = stack.enter_context(mock.patch.object(account, "_fetch_report",
                                                         side_effect=[[], []]))

    def run_pulse(self, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            account.cmd_pulse(ns(**kw))
        return (json.loads(out.getvalue()) if kw.get("json", True) else out.getvalue(),
                err.getvalue())

    def test_default_and_previous_complete_windows(self):
        data, err = self.run_pulse()
        self.assertEqual(data["period"], {"from": "2026-11-11", "to": "2026-11-17", "days": 7})
        self.assertEqual(data["comparePeriod"], {"from": "2026-11-04", "to": "2026-11-10"})
        self.assertEqual([c.args[2:4] for c in self.fetch.call_args_list],
                         [("2026-11-11", "2026-11-17"), ("2026-11-04", "2026-11-10")])
        self.assertEqual(self.api.call_args.args[1],
                         [{"dateFrom": "2026-11-11", "dateTo": "2026-11-17"}])
        self.assertIsNone(data["todayWarning"])
        self.assertEqual(err, "")

    def test_one_day_is_yesterday(self):
        data, _ = self.run_pulse(days=1)
        self.assertEqual(data["period"], {"from": "2026-11-17", "to": "2026-11-17", "days": 1})
        self.assertEqual(data["comparePeriod"], {"from": "2026-11-16", "to": "2026-11-16"})

    def test_explicit_dates_unchanged_and_today_warning(self):
        for end in ("2026-11-18", "2026-11-19"):
            with self.subTest(end=end):
                self.fetch.side_effect = [[], []]
                reports._today_stats_warned = False
                data, err = self.run_pulse(date_from="2026-11-12", date_to=end)
                self.assertEqual(data["period"]["from"], "2026-11-12")
                self.assertEqual(data["period"]["to"], end)
                self.assertEqual(data["comparePeriod"]["to"], "2026-11-11")
                self.assertIn("dnešek proto v datech chybí", data["todayWarning"])
                self.assertIn("dnešek", err)
                self.assertIn("Období proto nejsou přímo srovnatelná.", data["todayWarning"])
                self.assertEqual(err.count("Sklik API dnešní statistiky nevrací"), 1)

    def test_explicit_historical_window_and_no_compare(self):
        data, err = self.run_pulse(date_from="2026-10-01", date_to="2026-10-03", no_compare=True)
        self.assertEqual(data["period"]["days"], 3)
        self.assertIsNone(data["comparePeriod"])
        self.assertIsNone(data["todayWarning"])
        self.assertEqual(self.fetch.call_count, 1)
        self.assertNotIn("d_cost", data["totals"])
        self.assertEqual(err, "")

    def test_activity_and_backward_compatible_json(self):
        self.fetch.side_effect = [[row(1, "Delayed", conversions=2, conversionValue=300),
                                   row(2, "Inactive", impressions=0),
                                   row(3, "Stopped", impressions=0)],
                                  [row(3, "Stopped", totalMoney=10000),
                                   row(4, "Previous only", totalMoney=20000)]]
        data, _ = self.run_pulse()
        self.assertEqual(set(data), {"account", "period", "comparePeriod", "statsWarning",
                                     "todayWarning", "totals", "campaigns",
                                     "hiddenZeroImpressionCampaigns", "hiddenInactiveCampaigns", "movers"})
        self.assertEqual([r["id"] for r in data["campaigns"]], [1])
        self.assertEqual(data["campaigns"][0]["conversions"], 2)
        self.assertEqual(data["totals"]["convValue_czk"], 300)
        self.assertEqual(data["hiddenZeroImpressionCampaigns"], 3)
        self.assertEqual(data["hiddenInactiveCampaigns"], 2)
        self.assertIn("Stopped: cost ↓100%", data["movers"])
        self.assertIn("Previous only: cost ↓100%", data["movers"])
        self.assertEqual(data["totals"]["d_cost"], "↓100%")
        self.assertFalse(any(k.startswith("_") for k in data["campaigns"][0]))

    def test_each_activity_metric_keeps_campaign(self):
        self.assertIn("transactions", reports.STAT_COLUMNS)
        for metric in ("impressions", "clicks", "totalMoney", "conversions", "conversionValue", "transactions"):
            with self.subTest(metric=metric):
                self.fetch.side_effect = [[row(1, "Active", **{metric: 1})], []]
                data, _ = self.run_pulse()
                self.assertEqual(len(data["campaigns"]), 1)
                self.assertEqual(data["hiddenZeroImpressionCampaigns"], 0 if metric == "impressions" else 1)
                self.assertEqual(data["hiddenInactiveCampaigns"], 0)

    def test_text_shows_stopped_movers_even_without_current_activity(self):
        self.fetch.side_effect = [[row(1, "Inactive")], [row(2, "Stopped", totalMoney=100)]]
        out, _ = self.run_pulse(json=False)
        self.assertIn("Žádná kampaň s aktivitou v období.", out)
        self.assertIn("Skryté kampaně bez aktivity: 1", out)
        self.assertIn("Stopped: cost ↓100%", out)

    def test_readiness_warning_remains_separate(self):
        self.api.return_value = {"status": 200, "days": [{"date": "20261118T000000", "status": "preparing"}]}
        data, err = self.run_pulse(date_from="2026-11-18", date_to="2026-11-18")
        self.assertIn("preparing", data["statsWarning"])
        self.assertIn("dnešek proto v datech chybí", data["todayWarning"])
        self.assertEqual(err.count("Sklik API dnešní statistiky nevrací"), 1)

    def test_shared_report_warning_is_not_duplicated_in_pulse(self):
        self.fetch.side_effect = None
        self.fetch.side_effect = reports._fetch_report
        with mock.patch.object(reports, "_api_call", return_value={"reportId": 1, "totalCount": 0}):
            _, err = self.run_pulse(date_from="2026-11-18", date_to="2026-11-18")
        self.assertEqual(err.count("Sklik API dnešní statistiky nevrací"), 1)

    def test_legacy_counter_matches_original_filter(self):
        current = [row(1, "Normal", impressions=10),
                   row(2, "Delayed", conversions=1),
                   row(3, "Inactive", impressions=0),
                   row(4, "Null", impressions=None),
                   {"id": 5, "stats": None}]
        self.fetch.side_effect = [current, []]
        data, _ = self.run_pulse()
        # HEAD hid every row failing impressions > 0, including delayed conversions.
        head_hidden = len(current) - sum(
            (account._first_stats(r).get("impressions", 0) or 0) > 0 for r in current)
        self.assertEqual(data["hiddenZeroImpressionCampaigns"], head_hidden)
        self.assertEqual(head_hidden, 4)
        self.assertEqual(data["hiddenInactiveCampaigns"], 3)

    def test_nonpadded_historical_window_does_not_warn(self):
        for start, end in (("2026-11-1", "2026-11-9"), ("2026-1-30", "2026-2-01")):
            with self.subTest(end=end):
                self.fetch.side_effect = [[], []]
                data, err = self.run_pulse(date_from=start, date_to=end)
                self.assertIsNone(data["todayWarning"])
                self.assertEqual(err, "")
                self.assertFalse(reports._today_stats_warned)

    def test_text_warning_stays_visible_after_process_warning(self):
        for warned in (False, True):
            for compare in (True, False):
                with self.subTest(warned=warned, compare=compare):
                    reports._today_stats_warned = warned
                    self.fetch.side_effect = [[], []]
                    out, err = self.run_pulse(json=False, date_from="2026-11-18",
                                              date_to="2026-11-18", no_compare=not compare)
                    warning = reports._TODAY_STATS_WARNING
                    if compare:
                        warning += " Období proto nejsou přímo srovnatelná."
                    self.assertIn(warning, out.split("TOTAL")[0])
                    self.assertEqual(err, "")  # text mode: shown once, in the digest header
                    self.assertTrue(reports._today_stats_warned)
                    self.assertNotIn("includeCurrentDayStats", out + err)
                    if not compare:
                        self.assertNotIn("srovnatelná", out + err)

    def test_json_no_compare_warning_has_no_comparison_sentence(self):
        data, err = self.run_pulse(date_from="2026-11-18", date_to="2026-11-18", no_compare=True)
        self.assertEqual(data["todayWarning"], reports._TODAY_STATS_WARNING)
        self.assertEqual(err, f"⚠️  {data['todayWarning']}\n")


class TestReportTodayWarning(unittest.TestCase):
    def test_stats_commands_warn_once_per_process_without_changing_payload(self):
        err = io.StringIO()
        with mock.patch.object(reports, "datetime", wraps=datetime) as clock, \
                mock.patch.object(reports, "_today_stats_warned", False), \
                mock.patch.object(reports, "_api_call", return_value={"reportId": 1, "totalCount": 0}) as call, \
                contextlib.redirect_stderr(err):
            clock.now.return_value = TODAY
            reports._fetch_report("campaigns", {}, "2026-11-17", "2026-11-17")
            self.assertEqual(err.getvalue(), "")
            for entity in ("campaigns", "groups", "keywords", "ads"):
                reports._fetch_report(entity, {}, "2026-11-18", "2026-11-18")
            reports._fetch_report("queries", {}, "2026-11-18", "2026-11-19")
        self.assertEqual(err.getvalue().count("Sklik API dnešní statistiky nevrací"), 1)
        for c in call.call_args_list:
            self.assertEqual(c.args[1][1], {"statGranularity": "total"})

    def test_parsed_dates_and_invalid_dates(self):
        for end, expected in (("2026-11-9", False), ("2026-2-01", False),
                              ("2026-11-18", True), ("2026-12-1", True),
                              ("2027-1-1", True), ("not-a-date", False),
                              ("20261117", False), ("2026-02-30", False)):
            with self.subTest(end=end), \
                    mock.patch.object(reports, "_today_stats_warned", False), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                warning = reports._warn_today_stats(end, "2026-11-18")
                self.assertEqual(warning is not None, expected)
                self.assertEqual(bool(err.getvalue()), expected)
                self.assertEqual(reports._today_stats_warned, expected)

    def test_configuration_listings_do_not_warn_or_consume_flag(self):
        cases = [(placements, placements.cmd_placements, ns(group_id=None))]
        cases += [(display_targeting, display_targeting.cmd_targeting,
                   ns(group_id=None, type=kind, negative=False))
                  for kind in ("interest", "theme", "intend")]
        for module, command, args in cases:
            with self.subTest(command=command.__name__, kind=getattr(args, "type", None)), \
                    mock.patch.object(module, "datetime", wraps=datetime) as clock, \
                    mock.patch.object(reports, "datetime", wraps=datetime) as rclock, \
                    mock.patch.object(reports, "_today_stats_warned", False), \
                    mock.patch.object(reports, "_api_call", return_value={"reportId": 1, "totalCount": 0}), \
                    mock.patch.object(module, "_fetch_report", wraps=reports._fetch_report) as fetch, \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                clock.now.return_value = rclock.now.return_value = TODAY
                command(args)
                self.assertFalse(fetch.call_args.kwargs["warn_today"])
                self.assertEqual(err.getvalue(), "")
                self.assertFalse(reports._today_stats_warned)
                reports._fetch_report("campaigns", {}, "2026-11-18", "2026-11-18")
                self.assertEqual(err.getvalue().count(reports._TODAY_STATS_WARNING), 1)
                self.assertTrue(reports._today_stats_warned)


if __name__ == "__main__":
    unittest.main()
