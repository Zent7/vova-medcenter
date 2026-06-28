from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.doctor_rules import (  # noqa: E402
    is_male_sex,
    should_include_doctor_role_for_client_sex,
)


class DoctorRulesTests(unittest.TestCase):
    def test_male_sex_excludes_gynecologist(self):
        for sex in ["M", "male", "муж", "мужской"]:
            with self.subTest(sex=sex):
                self.assertFalse(should_include_doctor_role_for_client_sex("gynecologist", sex))

    def test_female_or_unknown_sex_keeps_gynecologist(self):
        for sex in ["F", "female", "жен", "", None]:
            with self.subTest(sex=sex):
                self.assertTrue(should_include_doctor_role_for_client_sex("gynecologist", sex))

    def test_male_sex_keeps_other_roles(self):
        self.assertTrue(should_include_doctor_role_for_client_sex("therapist", "M"))
        self.assertTrue(should_include_doctor_role_for_client_sex("dentist", "мужской"))

    def test_is_male_sex_does_not_match_female(self):
        self.assertFalse(is_male_sex("female"))


if __name__ == "__main__":
    unittest.main()
