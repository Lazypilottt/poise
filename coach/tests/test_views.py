import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from coach.analysis.pipeline import AnalysisResult
from coach.analysis.scoring import score_interview
from coach.analysis.speech import SpeechAnalysisError
from coach.models import InterviewSession

from .factories import make_posture, make_speech

TEMP_MEDIA = tempfile.mkdtemp(prefix="poise-test-media-")
PASSWORD = "Str0ng-pass-123"


def fake_result(video_path, snapshot_path=None):
    speech, posture = make_speech(), make_posture()
    if snapshot_path:
        Path(snapshot_path).parent.mkdir(parents=True, exist_ok=True)
        Path(snapshot_path).write_bytes(b"jpeg")
    return AnalysisResult(
        report=score_interview(speech, posture),
        speech=speech.to_dict(),
        posture=posture.to_dict(),
        snapshot_path=Path(snapshot_path) if snapshot_path else None,
        duration_s=speech.total_duration,
    )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ViewTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user("asha", "asha@example.com", PASSWORD)

    def login(self, user=None):
        self.client.force_login(user or self.user)

    def start_practice(self, **data):
        payload = {"role": "software", "level": "student", "skills": "Python", "question_count": 5}
        payload.update(data)
        return self.client.post(reverse("setup"), payload)

    def upload(self):
        return SimpleUploadedFile("interview.webm", b"\x1aE\xdf\xa3fake-webm", content_type="video/webm")


class PublicPagesTests(ViewTestCase):
    def test_home(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Poise")

    def test_protected_pages_redirect_to_login(self):
        for name in ("setup", "interview", "history", "account"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}", fetch_redirect_response=False)

    def test_contact_sends_email(self):
        response = self.client.post(
            reverse("contact"), {"name": "Ravi", "email": "ravi@example.com", "message": "Love it"}, follow=True
        )
        self.assertContains(response, "Your message has been sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ravi@example.com", mail.outbox[0].body)


class AuthTests(ViewTestCase):
    def test_signup_logs_user_in(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "newbie", "email": "new@example.com", "password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertRedirects(response, reverse("setup"))
        self.assertTrue(User.objects.filter(username="newbie").exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="newbie").pk)

    def test_signup_rejects_duplicate_email(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "other", "email": "ASHA@example.com", "password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertContains(response, "already exists")

    def test_login(self):
        response = self.client.post(reverse("login"), {"username": "asha", "password": PASSWORD})
        self.assertRedirects(response, reverse("setup"), fetch_redirect_response=False)

    def test_login_failure(self):
        response = self.client.post(reverse("login"), {"username": "asha", "password": "wrong"})
        self.assertContains(response, "Invalid username or password")

    def test_change_password(self):
        self.login()
        new = "An0ther-strong-pass"
        response = self.client.post(
            reverse("account"), {"old_password": PASSWORD, "new_password1": new, "new_password2": new}
        )
        self.assertRedirects(response, reverse("account"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))


class PracticeFlowTests(ViewTestCase):
    def test_setup_generates_questions(self):
        self.login()
        response = self.start_practice(skills="Rust, Go", question_count=3)
        self.assertRedirects(response, reverse("interview"))
        practice = self.client.session["practice_setup"]
        self.assertEqual(len(practice["questions"]), 3)

        response = self.client.get(reverse("interview"))
        self.assertContains(response, practice["questions"][0])

    def test_interview_without_setup_redirects(self):
        self.login()
        self.assertRedirects(self.client.get(reverse("interview")), reverse("setup"))

    @mock.patch("coach.analysis.pipeline.analyse_recording", side_effect=fake_result)
    def test_submit_creates_scored_session(self, analyse):
        self.login()
        self.start_practice()
        response = self.client.post(reverse("submit"), {"recording": self.upload()})

        self.assertEqual(response.status_code, 200)
        session = InterviewSession.objects.get()
        self.assertEqual(response.json()["redirect"], session.get_absolute_url())
        self.assertEqual(session.status, InterviewSession.Status.COMPLETE)
        self.assertEqual(session.user, self.user)
        self.assertGreater(session.overall_score, 0)
        self.assertTrue(session.snapshot.name.startswith("snapshots/"))
        analyse.assert_called_once()

        page = self.client.get(session.get_absolute_url())
        self.assertContains(page, "Interview report")
        self.assertContains(page, str(session.overall_score))

        # The snapshot is only served to its owner.
        snapshot_url = reverse("snapshot", args=[session.pk])
        self.assertEqual(b"".join(self.client.get(snapshot_url).streaming_content), b"jpeg")
        self.client.force_login(User.objects.create_user("eve", "eve@example.com", PASSWORD))
        self.assertEqual(self.client.get(snapshot_url).status_code, 404)

    @mock.patch(
        "coach.analysis.pipeline.analyse_recording",
        side_effect=SpeechAnalysisError("No speech was detected in the recording."),
    )
    def test_submit_reports_analysis_errors(self, _):
        self.login()
        self.start_practice()
        response = self.client.post(reverse("submit"), {"recording": self.upload()})
        self.assertEqual(response.status_code, 422)
        self.assertIn("No speech", response.json()["error"])
        self.assertEqual(InterviewSession.objects.get().status, InterviewSession.Status.FAILED)

    def test_submit_requires_recording(self):
        self.login()
        self.start_practice()
        response = self.client.post(reverse("submit"), {})
        self.assertEqual(response.status_code, 400)

    def test_submit_requires_setup(self):
        self.login()
        response = self.client.post(reverse("submit"), {"recording": self.upload()})
        self.assertEqual(response.status_code, 400)

    def test_submit_rejects_get(self):
        self.login()
        self.assertEqual(self.client.get(reverse("submit")).status_code, 405)


class SessionAccessTests(ViewTestCase):
    def make_session(self, user, score=70, **extra):
        return InterviewSession.objects.create(
            user=user,
            role="data",
            level="junior",
            questions=["Tell me about yourself."],
            status=InterviewSession.Status.COMPLETE,
            overall_score=score,
            report=score_interview(make_speech(), make_posture()),
            speech_metrics=make_speech().to_dict(),
            **extra,
        )

    def test_users_cannot_see_each_others_sessions(self):
        other = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        session = self.make_session(other)
        self.login()
        self.assertEqual(self.client.get(session.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.post(reverse("delete_session", args=[session.pk])).status_code, 404)

    def test_history_shows_stats_and_trend(self):
        for score in (55, 70, 85):
            self.make_session(self.user, score)
        self.login()
        response = self.client.get(reverse("history"))
        self.assertEqual(response.context["completed_count"], 3)
        self.assertEqual(response.context["best_score"], 85)
        self.assertEqual(response.context["average_score"], 70)
        self.assertTrue(response.context["trend_points"])

    def test_result_shows_change_from_previous(self):
        self.make_session(self.user, 60)
        latest = self.make_session(self.user, 72)
        self.login()
        response = self.client.get(latest.get_absolute_url())
        self.assertEqual(response.context["score_change"], 12)
        self.assertContains(response, "+12 vs. previous session")

    def test_delete_session(self):
        session = self.make_session(self.user)
        self.login()
        response = self.client.post(reverse("delete_session", args=[session.pk]))
        self.assertRedirects(response, reverse("history"))
        self.assertFalse(InterviewSession.objects.exists())
