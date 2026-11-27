"""Offline tests for the batch campaign-level negatives (negatives-campaign,
negative-campaign-add/remove) and their `network` handling (Fénix 1.40.0)."""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklik.commands import campaign_negatives  # noqa: E402
from test_fixes import ns, run  # noqa: E402


def _neg_list(items):
    """fenix.call stub: GET returns `items`, writes are recorded."""
    def fake(method, path, params=None, body=None):
        return {"items": items} if method == "GET" else None
    return fake


class TestCampaignNegativeNetwork(unittest.TestCase):
    EXISTING = [{"name": "zdarma", "matchType": "negativePhrase", "network": "context"}]

    def _args(self, **kw):
        base = dict(campaign_id=7, name="zdarma", match_type="negativePhrase",
                    keywords_json=None, network=None, confirm=True)
        base.update(kw)
        return ns(**base)

    def test_listing_asks_for_network(self):
        with mock.patch.object(campaign_negatives.fenix, "call",
                               side_effect=_neg_list(self.EXISTING)) as call:
            out, code = run(campaign_negatives.cmd_negatives_campaign, self._args())
        self.assertIsNone(code)
        self.assertIn("network", call.call_args_list[0].args[2]["a"])
        self.assertEqual(json.loads(out)[0]["network"], "context")

    def test_add_with_network_is_not_a_duplicate_of_other_network(self):
        with mock.patch.object(campaign_negatives.fenix, "call",
                               side_effect=_neg_list(self.EXISTING)) as call:
            out, _ = run(campaign_negatives.cmd_negative_campaign_add,
                         self._args(network="fulltext"))
        post = [c for c in call.call_args_list if c.args[0] == "POST"]
        self.assertEqual(len(post), 1)
        self.assertEqual(post[0].args[3]["network"], "fulltext")
        self.assertEqual(len(json.loads(out)["added"]), 1)

    def test_add_without_network_skips_but_flags_one_network_only(self):
        existing = self.EXISTING + [{"name": "jiné", "matchType": "negativeExact",
                                     "network": "fulltext"}]
        with mock.patch.object(campaign_negatives.fenix, "call",
                               side_effect=_neg_list(existing)) as call:
            out, _ = run(campaign_negatives.cmd_negative_campaign_add, self._args())
        self.assertFalse([c for c in call.call_args_list if c.args[0] == "POST"])
        res = json.loads(out)
        self.assertEqual(res["presentInOneNetworkOnly"][0]["onlyIn"], ["context"])

    def test_single_network_campaign_gets_no_note(self):
        # live 2026-11-22: a context campaign accepts only `context` negatives
        with mock.patch.object(campaign_negatives.fenix, "call",
                               side_effect=_neg_list(self.EXISTING)):
            out, _ = run(campaign_negatives.cmd_negative_campaign_add, self._args())
        self.assertNotIn("presentInOneNetworkOnly", json.loads(out))

    def test_remove_without_network_sends_no_network(self):
        with mock.patch.object(campaign_negatives.fenix, "call",
                               side_effect=_neg_list(self.EXISTING)) as call:
            out, _ = run(campaign_negatives.cmd_negative_campaign_remove, self._args())
        post = [c for c in call.call_args_list if c.args[0] == "POST"][0]
        self.assertTrue(post.args[1].endswith("delete"))
        self.assertNotIn("network", post.args[3])
        self.assertEqual(json.loads(out)["network"], "both")

    def test_remove_in_other_network_is_not_found(self):
        with mock.patch.object(campaign_negatives.fenix, "call",
                               side_effect=_neg_list(self.EXISTING)) as call:
            _, code = run(campaign_negatives.cmd_negative_campaign_remove,
                          self._args(network="fulltext"))
        self.assertEqual(code, 1)
        self.assertFalse([c for c in call.call_args_list if c.args[0] == "POST"])


if __name__ == "__main__":
    unittest.main()
