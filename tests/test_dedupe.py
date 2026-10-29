"""Dedupe tests. Run with: python -m unittest discover -s tests"""

import unittest

from opencam.dedupe import dedupe
from opencam.normalize import make_record


def rec(rid, t, lat, lon, source, **kw):
    return make_record(rid=rid, cam_type=t, lat=lat, lon=lon, source=source, **kw)


class DedupeTests(unittest.TestCase):
    def test_merges_same_camera_across_sources(self):
        a = rec("osm:node/1", "alpr", 32.7767, -96.7970, "osm", confidence=0.55)
        b = rec("deflock:9", "alpr", 32.77671, -96.79701, "deflock", confidence=0.6)
        out = dedupe([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["sources"], ["deflock", "osm"])
        self.assertGreater(out[0]["confidence"], 0.6)  # agreement bonus
        self.assertEqual(out[0]["id"], "deflock:9")      # smallest id wins

    def test_keeps_distant_cameras_separate(self):
        a = rec("osm:node/1", "alpr", 32.7767, -96.7970, "osm")
        b = rec("osm:node/2", "alpr", 32.8000, -96.7970, "osm")  # ~2.6 km away
        self.assertEqual(len(dedupe([a, b])), 2)

    def test_opposing_headings_not_merged(self):
        a = rec("osm:node/1", "speed_camera", 40.0, -75.0, "osm", direction=0)
        b = rec("osm:node/2", "speed_camera", 40.00001, -75.00001, "osm", direction=180)
        self.assertEqual(len(dedupe([a, b])), 2)

    def test_incompatible_types_not_merged(self):
        a = rec("osm:node/1", "alpr", 40.0, -75.0, "osm")
        b = rec("osm:node/2", "speed_camera", 40.00001, -75.00001, "osm")
        self.assertEqual(len(dedupe([a, b])), 2)


if __name__ == "__main__":
    unittest.main()
