import unittest

from services.running_course_service import GPXParseError, parse_gpx


SAMPLE_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="ON_FLOW" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Oncheoncheon 5K</name>
    <trkseg>
      <trkpt lat="35.2200" lon="129.0790"><ele>10</ele><time>2026-08-02T22:00:00Z</time></trkpt>
      <trkpt lat="35.2250" lon="129.0800"><ele>18</ele><time>2026-08-02T22:05:00Z</time></trkpt>
      <trkpt lat="35.2300" lon="129.0820"><ele>15</ele><time>2026-08-02T22:10:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""


class ParseGpxTests(unittest.TestCase):
    def test_parses_track_metadata_and_points(self):
        course = parse_gpx(SAMPLE_GPX, "fallback.gpx")

        self.assertEqual(course["name"], "Oncheoncheon 5K")
        self.assertEqual(course["point_count"], 3)
        self.assertEqual(course["elevation_gain_m"], 8)
        self.assertEqual(course["run_date"], "2026-08-02")
        self.assertEqual(course["duration_seconds"], 600)
        self.assertGreater(course["distance_km"], 1)
        self.assertEqual(len(course["paths"]), 1)
        self.assertEqual(course["paths"][0][0], [129.079, 35.22])

    def test_rejects_non_gpx_xml(self):
        with self.assertRaises(GPXParseError):
            parse_gpx(b"<root />")

    def test_rejects_entity_declarations(self):
        unsafe = b'<!DOCTYPE gpx [<!ENTITY x "value">]><gpx>&x;</gpx>'
        with self.assertRaises(GPXParseError):
            parse_gpx(unsafe)


if __name__ == "__main__":
    unittest.main()
