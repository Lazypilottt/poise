from django.test import SimpleTestCase

from coach.questions import CLOSER, OPENERS, ROLE_CHOICES, parse_skills, select_questions


class QuestionSelectionTests(SimpleTestCase):
    def test_count_and_structure(self):
        for role, _ in ROLE_CHOICES:
            for count in (3, 5):
                qs = select_questions(role, "junior", ["Python"], count, seed=1)
                self.assertEqual(len(qs), count)
                self.assertEqual(len(set(qs)), count, "questions must be unique")
                self.assertIn(qs[0], OPENERS)

    def test_five_question_session_ends_with_closer(self):
        self.assertEqual(select_questions("data", "student", [], 5, seed=3)[-1], CLOSER)

    def test_skill_is_personalised(self):
        qs = select_questions("software", "student", ["Kubernetes"], 5, seed=7)
        self.assertTrue(any("Kubernetes" in q for q in qs))

    def test_deterministic_with_seed(self):
        self.assertEqual(
            select_questions("product", "senior", ["SQL"], 5, seed=42),
            select_questions("product", "senior", ["SQL"], 5, seed=42),
        )

    def test_unknown_role_falls_back_to_general(self):
        self.assertEqual(len(select_questions("astronaut", "nope", None, 5, seed=0)), 5)

    def test_parse_skills(self):
        self.assertEqual(parse_skills(" Python, SQL ,,\nReact "), ["Python", "SQL", "React"])
        self.assertEqual(parse_skills(""), [])
