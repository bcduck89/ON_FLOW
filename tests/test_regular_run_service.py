import hashlib
import unittest
from datetime import date, time
from unittest.mock import patch

from services.regular_run_service import create_regular_run, parse_regular_run_text


class RegularRunTextParserTests(unittest.TestCase):
    def test_extracts_common_regular_run_fields_from_korean_text(self):
        raw_text = """
        정기 러닝: 온천천 수요런
        일시: 2026년 8월 20일 오후 7시 30분
        집결지: 동래역 4번 출구
        코스: 동래역 - 온천천 왕복
        거리: 8.5km
        페이스: 6:00/km
        참여 12명
        """

        result = parse_regular_run_text(
            raw_text,
            filename="regular-run.png",
            reference_date=date(2026, 8, 16),
        )

        self.assertEqual(result["title"], "온천천 수요런")
        self.assertEqual(result["run_date"], date(2026, 8, 20))
        self.assertEqual(result["start_time"], time(19, 30))
        self.assertEqual(result["location"], "동래역 4번 출구")
        self.assertEqual(result["course_name"], "동래역 - 온천천 왕복")
        self.assertEqual(result["distance_km"], 8.5)
        self.assertEqual(result["target_pace"], "6:00/km")
        self.assertEqual(result["participant_count"], 12)

    def test_uses_filename_when_no_title_is_recognized(self):
        result = parse_regular_run_text("", filename="8월 정기런.png")
        self.assertEqual(result["title"], "8월 정기런")


class RegularRunCreateTests(unittest.TestCase):
    @patch("services.regular_run_service.insert_regular_run")
    def test_normalizes_and_inserts_reviewed_values(self, insert_regular_run):
        insert_regular_run.side_effect = lambda row: row
        image_data = b"sample-image"

        result = create_regular_run(
            title="  온천천 정기런  ",
            run_date=date(2026, 8, 20),
            start_time=time(19, 30),
            location=" 동래역 4번 출구 ",
            course_name="온천천 왕복",
            distance_km=8.567,
            target_pace="6:00/km",
            participant_count=12,
            memo="우천 시 취소",
            source_image_name="capture.png",
            source_image_data=image_data,
            raw_ocr_text="원문",
            created_by="admin",
        )

        self.assertEqual(result["title"], "온천천 정기런")
        self.assertEqual(result["start_time"], "19:30:00")
        self.assertEqual(result["distance_km"], 8.57)
        self.assertEqual(
            result["source_hash"],
            hashlib.sha256(image_data).hexdigest(),
        )
        insert_regular_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
