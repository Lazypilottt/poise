from django.test import SimpleTestCase

from coach.analysis.posture import FrameAssessment, Point, assess_frame, line_tilt_degrees, summarise
from coach.analysis.scoring import band, grade, score_interview
from coach.analysis.speech import SpeechAnalysisError, parse_praat_output

from .factories import make_posture, make_speech

# Output captured from the Praat script on a real 10-second sample.
PRAAT_SAMPLE = "40\n3\n4\n5\n7.6\n10\n0.8\n105.03\n26.2\n100.3\n79\n307\n91\n111\n1\n"


class ParsePraatOutputTests(SimpleTestCase):
    def test_parses_all_fields(self):
        m = parse_praat_output(PRAAT_SAMPLE)
        self.assertEqual(m.syllables, 40)
        self.assertEqual(m.pauses, 3)
        self.assertEqual(m.speech_rate, 4.0)
        self.assertEqual(m.total_duration, 10.0)
        self.assertAlmostEqual(m.f0_mean, 105.03)
        self.assertEqual(m.pronunciation_prob, 1.0)

    def test_derived_metrics(self):
        m = parse_praat_output(PRAAT_SAMPLE)
        self.assertAlmostEqual(m.pauses_per_minute, 18.0)
        self.assertAlmostEqual(m.pitch_variation, 26.2 / 105.03)
        self.assertIn("pauses_per_minute", m.to_dict())

    def test_noisy_audio_message(self):
        with self.assertRaisesMessage(SpeechAnalysisError, "background noise"):
            parse_praat_output("A noisy background or unnatural-sounding speech detected. No result try again\n")

    def test_truncated_output(self):
        with self.assertRaises(SpeechAnalysisError):
            parse_praat_output("40\n3\n4\n")


def _landmarks(**overrides):
    """A person sitting upright and centred in a 640px-wide frame."""
    points = {
        "nose": Point(320, 200),
        "left_shoulder": Point(440, 330),
        "right_shoulder": Point(200, 330),
        "left_ear": Point(370, 190),
        "right_ear": Point(270, 190),
    }
    points.update(overrides)
    return points


class PostureGeometryTests(SimpleTestCase):
    def test_line_tilt(self):
        self.assertAlmostEqual(line_tilt_degrees(Point(0, 0), Point(10, 0)), 0)
        self.assertAlmostEqual(line_tilt_degrees(Point(0, 0), Point(10, 10)), 45)
        self.assertAlmostEqual(line_tilt_degrees(Point(10, 0), Point(0, 10)), 45)
        self.assertAlmostEqual(line_tilt_degrees(Point(0, 0), Point(0, 0)), 0)

    def test_good_posture(self):
        result = assess_frame(_landmarks(), 640)
        self.assertTrue(result.is_good, result.issues)

    def test_no_person(self):
        result = assess_frame(None, 640)
        self.assertFalse(result.person_detected)
        self.assertEqual(result.issues, ["not_visible"])

    def test_slouching(self):
        result = assess_frame(_landmarks(nose=Point(320, 300)), 640)
        self.assertIn("slouching", result.issues)

    def test_tilted_shoulders(self):
        result = assess_frame(_landmarks(left_shoulder=Point(440, 370)), 640)
        self.assertIn("shoulder_tilt", result.issues)

    def test_head_tilt(self):
        result = assess_frame(_landmarks(left_ear=Point(370, 220)), 640)
        self.assertIn("head_tilt", result.issues)

    def test_looking_away(self):
        result = assess_frame(_landmarks(nose=Point(365, 200)), 640)
        self.assertIn("looking_away", result.issues)

    def test_hidden_ear_counts_as_looking_away(self):
        result = assess_frame(_landmarks(left_ear=Point(370, 190, visibility=0.1)), 640)
        self.assertIn("looking_away", result.issues)

    def test_framing(self):
        self.assertIn("too_close", assess_frame(_landmarks(), 260).issues)
        self.assertIn("too_far", assess_frame(_landmarks(), 2000).issues)

    def test_summarise(self):
        report = summarise(
            [
                FrameAssessment(True),
                FrameAssessment(True, ["slouching"]),
                FrameAssessment(False, ["not_visible"]),
                FrameAssessment(True),
            ]
        )
        self.assertEqual(report.frames_analysed, 4)
        self.assertEqual(report.frames_with_person, 3)
        self.assertEqual(report.good_ratio, 0.5)
        self.assertEqual(report.issue_ratios, {"not_visible": 0.25, "slouching": 0.25})

    def test_summarise_empty(self):
        self.assertEqual(summarise([]).frames_analysed, 0)


class ScoringTests(SimpleTestCase):
    def test_band(self):
        self.assertEqual(band(5, 0, 4, 6, 10), 100)
        self.assertEqual(band(2, 0, 4, 6, 10), 50)
        self.assertEqual(band(8, 0, 4, 6, 10), 50)
        self.assertEqual(band(-1, 0, 4, 6, 10), 0)
        self.assertEqual(band(11, 0, 4, 6, 10), 0)

    def test_grade(self):
        self.assertEqual(grade(90), "Excellent")
        self.assertEqual(grade(75), "Good")
        self.assertEqual(grade(55), "Fair")
        self.assertEqual(grade(20), "Needs work")

    def test_strong_interview(self):
        report = score_interview(make_speech(), make_posture(good_ratio=0.95))
        self.assertGreaterEqual(report["overall"], 85)
        self.assertEqual(set(report["scores"]), {"pace", "fluency", "clarity", "expressiveness", "body_language"})
        self.assertTrue(all(t["positive"] for t in report["tips"]))

    def test_weak_interview_gets_specific_tips(self):
        speech = make_speech(speech_rate=6.0, pauses=30, balance=0.4, f0_std=4.0, pronunciation_prob=0.5)
        posture = make_posture(good_ratio=0.2, issue_ratios={"slouching": 0.6, "looking_away": 0.3})
        report = score_interview(speech, posture)
        self.assertLess(report["overall"], 50)
        messages = " ".join(t["message"] for t in report["tips"])
        self.assertIn("quickly", messages)
        self.assertIn("flat", messages)
        self.assertIn("Slouching", messages)
        self.assertIn("Look at the camera", messages)
        # Improvement tips come before praise.
        self.assertFalse(report["tips"][0]["positive"])

    def test_without_video_body_language_is_skipped(self):
        report = score_interview(make_speech(), None)
        self.assertNotIn("body_language", report["scores"])
        self.assertGreaterEqual(report["overall"], 85)
