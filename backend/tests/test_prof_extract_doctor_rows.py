from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    PROF_EXTRACT_CLEARED_DOCTOR_ROWS,
    PROF_EXTRACT_DOCTOR_ROWS,
    _prof_extract_doctor_row_values,
)


def exam(role_id, doctor_name, *, is_completed=True, completed_at=None, conclusion="Годен"):
    return SimpleNamespace(
        doctor_role_id=role_id,
        doctor_name=doctor_name,
        result_text="",
        diagnosis="",
        fields_json={"conclusion": conclusion},
        is_completed=is_completed,
        completed_at=completed_at,
    )


class ProfExtractDoctorRowsTests(unittest.TestCase):
    def test_completed_therapist_fills_therapist_row(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {"therapist": exam("therapist", "Казаков И.В.", completed_at=datetime(2026, 6, 23, 9, 30))},
            encounter,
        )

        self.assertEqual(rows[0], (32, "Терапевт Казаков И.В.", date(2026, 6, 23), "годен"))

    def test_uncompleted_or_missing_roles_are_empty(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {"therapist": exam("therapist", "Казаков И.В.", is_completed=False)},
            encounter,
        )

        self.assertEqual(rows[0], (32, "", "", ""))
        gynecologist_row = rows[[role for role, _, _ in PROF_EXTRACT_DOCTOR_ROWS].index("gynecologist")]
        self.assertEqual(gynecologist_row, (45, "", "", ""))

    def test_psychiatrist_narcologist_is_not_exported(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {
                "psychiatrist": exam("psychiatrist", "Аносов И.Е."),
                "psychiatrist-narcologist": exam("psychiatrist-narcologist", "Аносов И.Е."),
            },
            encounter,
        )

        self.assertEqual(rows[1], (34, "Психиатр Аносов И.Е.", date(2026, 6, 24), "годен"))
        self.assertNotIn(37, [row[0] for row in rows])
        self.assertEqual(PROF_EXTRACT_CLEARED_DOCTOR_ROWS, (37,))

    def test_rows_keep_template_order(self):
        rows = _prof_extract_doctor_row_values({}, None)

        self.assertEqual(
            [(role_id, row_index) for role_id, _, row_index in PROF_EXTRACT_DOCTOR_ROWS],
            [
                ("therapist", 32),
                ("psychiatrist", 34),
                ("neurologist", 39),
                ("otolaryngologist", 41),
                ("surgeon", 43),
                ("gynecologist", 45),
                ("ophthalmologist", 48),
                ("dermatologist", 50),
                ("dentist", 52),
            ],
        )
        self.assertEqual([row[0] for row in rows], [row_index for _, _, row_index in PROF_EXTRACT_DOCTOR_ROWS])


if __name__ == "__main__":
    unittest.main()
