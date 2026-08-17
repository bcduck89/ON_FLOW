import hashlib
import unittest
from datetime import date, time
from unittest.mock import patch

import pandas as pd

from services.regular_run_service import (
    _paddle_result_to_lines,
    create_manual_regular_run,
    create_regular_run,
    default_run_type_for_date,
    delete_regular_run,
    get_regular_run_list,
    match_attendee_names_to_members,
    parse_regular_run_text,
    update_regular_run,
)
from utils.weekday_utils import get_korean_weekday


class RegularRunTextParserTests(unittest.TestCase):
    def test_converts_paddle_result_into_positioned_lines(self):
        lines = _paddle_result_to_lines(
            [
                {
                    "rec_texts": ["신우식", "낮은 신뢰도", "윤성철", "현규"],
                    "rec_scores": [0.99, 0.2, 0.98, 0.97],
                    "rec_boxes": [
                        [110, 80, 180, 112],
                        [110, 115, 180, 130],
                        [110, 140, 180, 173],
                        [110, 220, 170, 250],
                    ],
                }
            ]
        )

        self.assertEqual([line["text"] for line in lines], ["신우식", "윤성철", "현규"])
        self.assertEqual([line["height"] for line in lines], [32, 33, 30])

    def test_prefers_large_name_rows_over_attendee_status_messages(self):
        ocr_lines = [
            {"text": "7/12일 오후 8:00 정모 참석자 (3명)", "left": 30, "top": 20, "height": 24},
            {"text": "신우식", "left": 110, "top": 80, "height": 31},
            {"text": "윤성철", "left": 110, "top": 140, "height": 32},
            {"text": "화이팅", "left": 110, "top": 170, "height": 20},
            {"text": "현규", "left": 110, "top": 225, "height": 30},
        ]

        result = parse_regular_run_text(
            "\n".join(line["text"] for line in ocr_lines),
            filename="attendance.png",
            reference_date=date(2026, 8, 16),
            ocr_lines=ocr_lines,
        )

        self.assertEqual(result["attendee_names"], ["신우식", "윤성철", "현규"])

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

    def test_prefers_attendance_header_date_over_other_screen_date(self):
        raw_text = """
        2026.08.16
        7/12일 오후 8:00 정모 참석자 (3명)
        신우식
        윤성철
        현규
        """

        result = parse_regular_run_text(
            raw_text,
            filename="capture.png",
            reference_date=date(2026, 8, 17),
        )

        self.assertEqual(result["run_date"], date(2026, 7, 12))

    def test_reads_spaced_full_width_short_date(self):
        result = parse_regular_run_text(
            "8 ／ 14일 오후 7:00 정모 참석자 (1명)\n김주희",
            reference_date=date(2026, 8, 17),
        )

        self.assertEqual(result["run_date"], date(2026, 8, 14))

    def test_infers_previous_year_for_nearby_december_date(self):
        result = parse_regular_run_text(
            "12/31일 오후 8:00 정모 참석자 (1명)\n김주희",
            reference_date=date(2026, 1, 2),
        )

        self.assertEqual(result["run_date"], date(2025, 12, 31))

    def test_uses_filename_date_when_ocr_text_has_no_date(self):
        result = parse_regular_run_text(
            "정모 참석자 (1명)\n김주희",
            filename="2026-08-14_참석자.png",
            reference_date=date(2026, 8, 17),
        )

        self.assertEqual(result["run_date"], date(2026, 8, 14))

    def test_uses_filename_when_no_title_is_recognized(self):
        result = parse_regular_run_text("", filename="8월 정기런.png")
        self.assertEqual(result["title"], "8월 정기런")

    def test_converts_date_to_korean_weekday(self):
        self.assertEqual(get_korean_weekday(date(2026, 7, 12)), "일요일")

    @patch("services.regular_run_service.list_regular_runs")
    def test_builds_attendance_focused_list(self, list_regular_runs):
        list_regular_runs.return_value = [
            {
                "run_type": "자유",
                "run_date": "2026-07-12",
                "start_time": "20:00:00",
                "distance_km": 5.0,
                "participant_count": 3,
                "attendee_names": ["신우식", "윤성철", "현규"],
            }
        ]

        result = get_regular_run_list()

        self.assertEqual(
            result.columns.tolist(),
            [
                "번호",
                "구분",
                "날짜",
                "요일",
                "시간",
                "코스 이름",
                "거리 (km)",
                "뒷풀이",
                "총 참석인원",
                "참석자 명단",
            ],
        )
        self.assertEqual(result.iloc[0]["번호"], 1)
        self.assertEqual(result.iloc[0]["구분"], "자유")
        self.assertEqual(result.iloc[0]["뒷풀이"], "없음")
        self.assertEqual(result.iloc[0]["요일"], "일요일")
        self.assertEqual(result.iloc[0]["참석자 명단"], "신우식, 윤성철, 현규")

    @patch("services.regular_run_service.list_regular_runs")
    def test_numbers_newest_first_rows_by_chronological_sequence(
        self,
        list_regular_runs,
    ):
        list_regular_runs.return_value = [
            {"run_date": "2026-08-17", "attendee_names": []},
            {"run_date": "2026-08-10", "attendee_names": []},
            {"run_date": "2026-08-03", "attendee_names": []},
        ]

        result = get_regular_run_list()

        self.assertEqual(result["번호"].tolist(), [3, 2, 1])

    def test_sets_sunday_to_regular_and_other_days_to_free(self):
        self.assertEqual(default_run_type_for_date(date(2026, 7, 12)), "정기")
        self.assertEqual(default_run_type_for_date(date(2026, 7, 13)), "자유")

    def test_matches_member_nickname_to_actual_name(self):
        members = pd.DataFrame(
            [
                {"name": "김주희", "nickname": "주히"},
                {"name": "신우식", "nickname": "우식"},
            ]
        )

        result = match_attendee_names_to_members(
            ["주히", "신우식", "비회원"],
            members=members,
        )

        self.assertEqual(result, ["김주희", "신우식", "비회원"])


class RegularRunCreateTests(unittest.TestCase):
    @patch("services.regular_run_service.insert_regular_run")
    def test_creates_manual_run_without_source_image(self, insert_regular_run):
        insert_regular_run.side_effect = lambda row: row

        result = create_manual_regular_run(
            run_type="자유",
            run_date=date(2026, 8, 17),
            start_time=time(19, 30),
            course_name="온천천 왕복",
            distance_km=5.0,
            after_party="없음",
            attendee_names=["김주희", "신우식"],
            created_by="admin",
        )

        self.assertEqual(result["participant_count"], 2)
        self.assertEqual(result["source_image_name"], "")
        self.assertIsNone(result["source_image_path"])
        self.assertEqual(len(result["source_hash"]), 64)
        insert_regular_run.assert_called_once()

    @patch("services.regular_run_service.find_regular_run_by_source_hash")
    @patch("services.regular_run_service.remove_regular_run_image")
    @patch("services.regular_run_service.upload_regular_run_image")
    @patch("services.regular_run_service.insert_regular_run")
    def test_normalizes_and_inserts_reviewed_values(
        self,
        insert_regular_run,
        upload_regular_run_image,
        remove_regular_run_image,
        find_regular_run_by_source_hash,
    ):
        insert_regular_run.side_effect = lambda row: row
        find_regular_run_by_source_hash.return_value = None
        image_data = b"sample-image"

        result = create_regular_run(
            run_type="정기",
            title="  온천천 정기런  ",
            run_date=date(2026, 8, 20),
            start_time=time(19, 30),
            location=" 동래역 4번 출구 ",
            course_name="온천천 왕복",
            distance_km=8.567,
            target_pace="6:00/km",
            after_party="카페",
            participant_count=12,
            attendee_names=[f"참석자{index}" for index in range(1, 13)],
            memo="우천 시 취소",
            source_image_name="capture.png",
            source_image_data=image_data,
            raw_ocr_text="원문",
            created_by="admin",
        )

        self.assertEqual(result["title"], "온천천 정기런")
        self.assertEqual(result["run_type"], "정기")
        self.assertEqual(result["start_time"], "19:30:00")
        self.assertEqual(result["after_party"], "카페")
        self.assertEqual(result["distance_km"], 8.57)
        self.assertEqual(len(result["attendee_names"]), 12)
        self.assertEqual(
            result["source_hash"],
            hashlib.sha256(image_data).hexdigest(),
        )
        insert_regular_run.assert_called_once()
        upload_regular_run_image.assert_called_once()
        remove_regular_run_image.assert_not_called()
        find_regular_run_by_source_hash.assert_called_once()

    @patch("services.regular_run_service.update_regular_run_row")
    def test_updates_reviewed_regular_run_values(self, update_regular_run_row):
        update_regular_run_row.side_effect = lambda run_id, values: {
            "regular_run_id": run_id,
            **values,
        }

        result = update_regular_run(
            regular_run_id=7,
            run_type="자유",
            run_date=date(2026, 8, 17),
            start_time=time(19, 30),
            course_name="온천천 왕복",
            distance_km=6.25,
            after_party="식사",
            participant_count=2,
            attendee_names=["김주희", "신우식"],
        )

        self.assertEqual(result["regular_run_id"], 7)
        self.assertEqual(result["run_type"], "자유")
        self.assertEqual(result["course_name"], "온천천 왕복")
        self.assertEqual(result["after_party"], "식사")
        self.assertEqual(result["distance_km"], 6.25)
        self.assertEqual(result["participant_count"], 2)

    @patch("services.regular_run_service.update_regular_run_row")
    def test_rejects_invalid_after_party(self, update_regular_run_row):
        with self.assertRaisesRegex(ValueError, "뒷풀이는"):
            update_regular_run(
                regular_run_id=7,
                run_type="자유",
                run_date=date(2026, 8, 17),
                start_time=time(19, 30),
                course_name="온천천 왕복",
                distance_km=5.0,
                after_party="미정",
                participant_count=1,
                attendee_names=["김주희"],
            )

        update_regular_run_row.assert_not_called()


class RegularRunDeleteTests(unittest.TestCase):
    def test_rejects_incorrect_admin_password(self):
        with (
            patch(
                "services.regular_run_service.verify_admin_password",
                return_value=False,
            ),
            patch("services.regular_run_service.delete_regular_run_row") as delete,
        ):
            with self.assertRaises(PermissionError):
                delete_regular_run(7, "wrong-password", "2026/08/capture.png")

        delete.assert_not_called()

    def test_deletes_record_and_source_image(self):
        with (
            patch(
                "services.regular_run_service.verify_admin_password",
                return_value=True,
            ),
            patch("services.regular_run_service.delete_regular_run_row") as delete,
            patch("services.regular_run_service.remove_regular_run_image") as remove,
        ):
            delete_regular_run("7", "correct-password", "2026/08/capture.png")

        delete.assert_called_once_with(7)
        remove.assert_called_once_with("2026/08/capture.png")

    def test_deletes_record_without_an_image(self):
        with (
            patch(
                "services.regular_run_service.verify_admin_password",
                return_value=True,
            ),
            patch("services.regular_run_service.delete_regular_run_row") as delete,
            patch("services.regular_run_service.remove_regular_run_image") as remove,
        ):
            delete_regular_run(7, "correct-password")

        delete.assert_called_once_with(7)
        remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
