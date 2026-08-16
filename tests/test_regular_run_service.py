import hashlib
import unittest
from datetime import date, time
from unittest.mock import patch

from services.regular_run_service import (
    create_regular_run,
    get_korean_weekday,
    get_regular_run_list,
    parse_regular_run_text,
)


class RegularRunTextParserTests(unittest.TestCase):
    def test_extracts_somoim_attendance_fields_from_korean_text(self):
        raw_text = """
        16:04
        참석자
        카카오톡으로 정모 공유하기
        7/12일 오후 8:00 정모 참석자 (3명)
        신 우 식
        윤 성 철
        화이팅
        현 규
        """

        result = parse_regular_run_text(
            raw_text,
            filename="regular-run.png",
            reference_date=date(2026, 8, 16),
        )

        self.assertEqual(result["run_date"], date(2026, 7, 12))
        self.assertEqual(result["weekday"], "일요일")
        self.assertEqual(result["start_time"], time(20, 0))
        self.assertEqual(result["participant_count"], 3)
        self.assertEqual(result["attendee_names"], ["신우식", "윤성철", "현규"])

    def test_uses_filename_when_no_title_is_recognized(self):
        result = parse_regular_run_text("", filename="8월 정기런.png")
        self.assertEqual(result["title"], "8월 정기런")

    def test_converts_date_to_korean_weekday(self):
        self.assertEqual(get_korean_weekday(date(2026, 7, 12)), "일요일")

    @patch("services.regular_run_service.list_regular_runs")
    def test_builds_attendance_focused_list(self, list_regular_runs):
        list_regular_runs.return_value = [
            {
                "run_date": "2026-07-12",
                "start_time": "20:00:00",
                "participant_count": 3,
                "attendee_names": ["신우식", "윤성철", "현규"],
            }
        ]

        result = get_regular_run_list()

        self.assertEqual(
            result.columns.tolist(),
            ["날짜", "요일", "시간", "총 참석인원", "참석자 명단"],
        )
        self.assertEqual(result.iloc[0]["요일"], "일요일")
        self.assertEqual(result.iloc[0]["참석자 명단"], "신우식, 윤성철, 현규")


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
            attendee_names=[f"참석자{index}" for index in range(1, 13)],
            memo="우천 시 취소",
            source_image_name="capture.png",
            source_image_data=image_data,
            raw_ocr_text="원문",
            created_by="admin",
        )

        self.assertEqual(result["title"], "온천천 정기런")
        self.assertEqual(result["start_time"], "19:30:00")
        self.assertEqual(result["distance_km"], 8.57)
        self.assertEqual(len(result["attendee_names"]), 12)
        self.assertEqual(
            result["source_hash"],
            hashlib.sha256(image_data).hexdigest(),
        )
        insert_regular_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
