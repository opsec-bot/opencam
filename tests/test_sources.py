"""Unit tests for the municipal and mobile source adapters (no network)."""

import datetime as dt
import json
import os
import tempfile
import unittest

from opencam.sources import mobile, municipal


class MunicipalHelpers(unittest.TestCase):
    def test_approach_codes_to_degrees(self):
        self.assertEqual(municipal._approach_to_deg({"first_approach": "WB"}, ("first_approach",)), 270.0)
        self.assertEqual(municipal._approach_to_deg({"first_approach": "nb"}, ("first_approach",)), 0.0)
        # Falls through to the second field when the first is blank.
        self.assertEqual(
            municipal._approach_to_deg({"first_approach": "", "second_approach": "EB"},
                                       ("first_approach", "second_approach")), 90.0)
        self.assertIsNone(municipal._approach_to_deg({"first_approach": "??"}, ("first_approach",)))

    def test_coord_flat_and_nested(self):
        self.assertEqual(municipal._coord({"latitude": "41.5"}, "latitude", "location"), 41.5)
        self.assertEqual(
            municipal._coord({"location_1": {"latitude": "39.1"}}, "latitude", "location_1"), 39.1)
        self.assertIsNone(municipal._coord({}, "latitude", "location"))


class MobileExpiry(unittest.TestCase):
    def _run_with(self, entries):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mobile_lprs.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(entries, fh)
            orig = mobile._DATA_PATH
            mobile._DATA_PATH = path
            try:
                bbox = {"south": -90, "north": 90, "west": -180, "east": 180}
                return mobile.fetch_region("us-xx", bbox)
            finally:
                mobile._DATA_PATH = orig

    def test_fresh_entry_kept_and_decayed(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        recs = self._run_with([{"lat": 38.9, "lon": -77.0, "lastVerified": today, "ttlDays": 45}])
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["type"], "alpr")
        self.assertEqual(recs[0]["sources"], ["mobile"])
        self.assertAlmostEqual(recs[0]["confidence"], 0.5, places=2)  # age 0 -> full base

    def test_expired_entry_dropped(self):
        old = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=60)).isoformat()
        recs = self._run_with([{"lat": 38.9, "lon": -77.0, "lastVerified": old, "ttlDays": 45}])
        self.assertEqual(recs, [])

    def test_undated_entry_dropped(self):
        recs = self._run_with([{"lat": 38.9, "lon": -77.0}])
        self.assertEqual(recs, [])

    def test_bbox_filter_excludes_outside(self):
        # Entry is fresh but far outside the (0,0)-(10,10) box, so it drops.
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mobile_lprs.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([{"lat": 38.9, "lon": -77.0, "lastVerified": today}], fh)
            orig = mobile._DATA_PATH
            mobile._DATA_PATH = path
            try:
                recs = mobile.fetch_region("x", {"south": 0, "north": 10, "west": 0, "east": 10})
            finally:
                mobile._DATA_PATH = orig
        self.assertEqual(recs, [])


if __name__ == "__main__":
    unittest.main()
