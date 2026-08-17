import base64
import unittest
from datetime import date
from unittest.mock import patch

from services.running_course_service import (
    GPXParseError,
    delete_running_course,
    parse_gpx,
    register_running_course,
    update_running_course,
)


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
        self.assertEqual(base64.b64decode(course["gpx_raw_base64"]), SAMPLE_GPX)
        self.assertEqual(course["gpx_filename"], "fallback.gpx")
        self.assertEqual(course["gpx_size_bytes"], len(SAMPLE_GPX))

    def test_rejects_non_gpx_xml(self):
        with self.assertRaises(GPXParseError):
            parse_gpx(b"<root />")

    def test_rejects_entity_declarations(self):
        unsafe = b'<!DOCTYPE gpx [<!ENTITY x "value">]><gpx>&x;</gpx>'
        with self.assertRaises(GPXParseError):
            parse_gpx(unsafe)


class SaveRunningCourseTests(unittest.TestCase):
    def test_registration_keeps_original_gpx_fields(self):
        parsed = parse_gpx(SAMPLE_GPX, "oncheon.gpx")

        with patch(
            "services.running_course_service.insert_course",
            side_effect=lambda row: row,
        ) as insert:
            saved = register_running_course(
                "온천천",
                date(2026, 8, 3),
                "부산",
                "야간 코스",
                ["정규런"],
                "admin",
                parsed,
            )

        insert.assert_called_once()
        self.assertEqual(base64.b64decode(saved["gpx_raw_base64"]), SAMPLE_GPX)
        self.assertEqual(saved["gpx_filename"], "oncheon.gpx")
        self.assertEqual(saved["gpx_size_bytes"], len(SAMPLE_GPX))

    def test_updates_editable_course_metadata_only(self):
        with patch(
            "services.running_course_service.update_course",
            side_effect=lambda course_id, row: {"activity_id": course_id, **row},
        ) as update:
            saved = update_running_course(
                9,
                "  수정 코스  ",
                date(2026, 8, 10),
                "  동래  ",
                "  설명  ",
                [" 정기 ", "", "야간"],
            )

        update.assert_called_once()
        self.assertEqual(saved["name"], "수정 코스")
        self.assertEqual(saved["run_date"], "2026-08-10")
        self.assertEqual(saved["location_name"], "동래")
        self.assertEqual(saved["tags"], ["정기", "야간"])
        self.assertNotIn("paths", saved)
        self.assertNotIn("gpx_raw_base64", saved)


class DeleteRunningCourseTests(unittest.TestCase):
    def test_rejects_incorrect_admin_password(self):
        with (
            patch(
                "services.running_course_service.verify_admin_password",
                return_value=False,
            ),
            patch("services.running_course_service.delete_course") as delete,
        ):
            with self.assertRaises(PermissionError):
                delete_running_course(7, "wrong-password")

        delete.assert_not_called()

    def test_deletes_course_after_password_verification(self):
        with (
            patch(
                "services.running_course_service.verify_admin_password",
                return_value=True,
            ),
            patch("services.running_course_service.delete_course") as delete,
        ):
            delete_running_course("7", "correct-password")

        delete.assert_called_once_with(7)

    def test_reports_supabase_delete_failure_without_leaking_details(self):
        with (
            patch(
                "services.running_course_service.verify_admin_password",
                return_value=True,
            ),
            patch(
                "services.running_course_service.delete_course",
                side_effect=Exception("sensitive backend details"),
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "관리자 Secret 키가 유효한지 확인",
            ) as context:
                delete_running_course(7, "correct-password")

        self.assertNotIn("sensitive backend details", str(context.exception))


if __name__ == "__main__":
    unittest.main()
