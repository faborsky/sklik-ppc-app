"""Offline tests: api.limits without userId, ad-update sends adType."""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sklik.api as api  # noqa: E402
from sklik.commands import account, ads  # noqa: E402
from test_fixes import ns, run  # noqa: E402


class TestApiLimitsNoUserId(unittest.TestCase):
    def test_api_limits_command_sends_no_user_id(self):
        with mock.patch.object(account, "_api_call",
                               return_value={"limits": {}, "batchCallLimits": []}) as call:
            run(account.cmd_api_limits, ns(user_id=123))
        self.assertNotIn("user_id", call.call_args.kwargs)
        self.assertEqual(len(call.call_args.args), 1)

    def test_ensure_limits_is_soft_and_without_user_id(self):
        calls = []

        def fake(method, *a, **kw):
            calls.append((method, a, kw))
            return {"status": 400, "statusMessage": "bad"}

        with mock.patch.object(api, "_api_call", side_effect=fake),                 mock.patch.object(api, "_load_rate_state", return_value={}),                 mock.patch.object(api, "_save_rate_state"):
            result = api._ensure_limits(123)
        method, a, kw = [c for c in calls if c[0] == "api.limits"][0]
        self.assertNotIn("user_id", kw)
        self.assertTrue(kw.get("_soft"))
        # a 400 keeps the fallbacks instead of failing
        self.assertEqual(result["page"], api.LIST_PAGE_SIZE_FALLBACK)


class TestAdUpdateSendsType(unittest.TestCase):
    def _run(self, ad_type):
        def fake(method, params, uid=None, **kw):
            if method == "ads.list":
                return {"ads": [{"id": 5, "adType": ad_type}]}
            return {"newAdIds": []}
        with mock.patch.object(ads, "_api_call", side_effect=fake) as call:
            out, code = run(ads.cmd_ad_update, ns(ad_id=5, status="suspend"))
        return call, out, code

    def test_combined_ad_gets_type(self):
        call, out, code = self._run("combined")
        self.assertIsNone(code)
        update = call.call_args_list[-1].args[1][0][0]
        self.assertEqual(update, {"id": 5, "adType": "combined", "status": "suspend"})

    def test_dynamic_banner_is_camel_case(self):
        call, _, _ = self._run("dynamic_banner")
        self.assertEqual(call.call_args_list[-1].args[1][0][0]["adType"], "dynamicBanner")

    def test_image_banner_is_refused(self):
        call, out, code = self._run("banner")
        self.assertEqual(code, 1)
        self.assertEqual([c.args[0] for c in call.call_args_list], ["ads.list"])
        self.assertIn("banner-update", json.loads(out)["error"]["message"])


if __name__ == "__main__":
    unittest.main()
