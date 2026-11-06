"""Create a demo user with a few past sessions so the UI can be explored
without recording anything:  python manage.py seed_demo
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from coach.analysis.posture import PostureReport
from coach.analysis.scoring import score_interview
from coach.analysis.speech import SpeechMetrics
from coach.models import InterviewSession
from coach.questions import select_questions

# Each entry nudges the metrics so scores improve over time.
PROGRESSION = [
    dict(speech_rate=5.6, pauses=26, balance=0.52, f0_std=8, pronunciation_prob=0.68, good=0.3, issues={"slouching": 0.45, "looking_away": 0.35}),
    dict(speech_rate=5.3, pauses=22, balance=0.57, f0_std=10, pronunciation_prob=0.72, good=0.42, issues={"slouching": 0.35, "looking_away": 0.3}),
    dict(speech_rate=5.1, pauses=19, balance=0.6, f0_std=11, pronunciation_prob=0.75, good=0.5, issues={"looking_away": 0.35, "head_tilt": 0.2}),
    dict(speech_rate=4.9, pauses=17, balance=0.64, f0_std=13, pronunciation_prob=0.78, good=0.6, issues={"looking_away": 0.3}),
    dict(speech_rate=4.7, pauses=15, balance=0.68, f0_std=14.5, pronunciation_prob=0.8, good=0.7, issues={"looking_away": 0.22}),
    dict(speech_rate=4.6, pauses=14, balance=0.71, f0_std=14.5, pronunciation_prob=0.84, good=0.76, issues={"looking_away": 0.24}),
]
ROLES = ["software", "software", "data", "software", "data", "software"]


class Command(BaseCommand):
    help = "Create a demo user (demo / poise-demo-123) with sample interview sessions."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="poise-demo-123")

    def handle(self, *args, username, password, **options):
        user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
        user.set_password(password)
        user.save()
        InterviewSession.objects.filter(user=user).delete()

        now = timezone.now()
        for i, (p, role) in enumerate(zip(PROGRESSION, ROLES)):
            total = 150.0 + 20 * i
            speech = SpeechMetrics(
                syllables=int(p["speech_rate"] * total),
                pauses=int(p["pauses"] * total / 60),
                speech_rate=p["speech_rate"],
                articulation_rate=round(p["speech_rate"] / p["balance"], 1),
                speaking_duration=round(total * p["balance"], 1),
                total_duration=total,
                balance=p["balance"],
                f0_mean=135.0,
                f0_std=float(p["f0_std"]),
                f0_median=131.0,
                f0_min=82.0,
                f0_max=262.0,
                f0_q25=118.0,
                f0_q75=150.0,
                pronunciation_prob=p["pronunciation_prob"],
            )
            posture = PostureReport(int(total), int(total), p["good"], p["issues"])
            report = score_interview(speech, posture)
            session = InterviewSession.objects.create(
                user=user,
                role=role,
                level="student",
                questions=select_questions(role, "student", ["Python", "SQL"], 5, seed=i),
                status=InterviewSession.Status.COMPLETE,
                overall_score=report["overall"],
                report=report,
                speech_metrics=speech.to_dict(),
                posture_metrics=posture.to_dict(),
                duration_seconds=total,
            )
            InterviewSession.objects.filter(pk=session.pk).update(
                created_at=now - timedelta(days=4 * (len(PROGRESSION) - 1 - i), hours=i)
            )

        self.stdout.write(self.style.SUCCESS(f"Demo user '{username}' ready with {len(PROGRESSION)} sessions."))
