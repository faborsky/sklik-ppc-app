"""Offline tests: Nákupy commands find the only Zboží shop without a premiseId."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklik.commands import nakupy  # noqa: E402
from test_fixes import ns  # noqa: E402


class TestPremiseAuto(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in list(os.environ):
            if k.startswith("SKLIK_FENIX_PREMISE"):
                del os.environ[k]

    def tearDown(self):
        self.env.stop()

    def _shops(self, *ids):
        return {"items": [{"id": i, "name": f"Z{i}", "zboziPremiseId": p}
                          for i, p in enumerate(ids)]}

    def test_explicit_premise_wins(self):
        with mock.patch.object(nakupy.fenix, "resolve_premise", return_value=7) as res, \
                mock.patch.object(nakupy.fenix, "call") as call:
            self.assertEqual(nakupy._premise(ns(premise_id=7)), 7)
        res.assert_called_once_with(7)
        call.assert_not_called()

    def test_single_shop_is_detected(self):
        with mock.patch.object(nakupy.fenix, "call", return_value=self._shops(555)):
            self.assertEqual(nakupy._premise(ns(premise_id=None)), 555)

    def test_several_shops_fail_with_list(self):
        with mock.patch.object(nakupy.fenix, "call", return_value=self._shops(1, 2)), \
                self.assertRaises(SystemExit):
            nakupy._premise(ns(premise_id=None))

    def test_no_shop_falls_back_to_config_error(self):
        with mock.patch.object(nakupy.fenix, "call", return_value={"items": []}), \
                mock.patch.object(nakupy.fenix, "resolve_premise",
                                  side_effect=SystemExit(1)) as res, \
                self.assertRaises(SystemExit):
            nakupy._premise(ns(premise_id=None))
        res.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
