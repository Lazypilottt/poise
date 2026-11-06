from django.conf import settings
from django.db import models
from django.urls import reverse

from .analysis.scoring import LABELS


class InterviewSession(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    role = models.CharField(max_length=32)
    level = models.CharField(max_length=32)
    questions = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROCESSING)

    overall_score = models.PositiveSmallIntegerField(null=True, blank=True)
    report = models.JSONField(default=dict, blank=True)
    speech_metrics = models.JSONField(default=dict, blank=True)
    posture_metrics = models.JSONField(default=dict, blank=True)
    snapshot = models.FileField(upload_to="snapshots/", blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} - {self.get_role_display()} ({self.created_at:%Y-%m-%d})"

    def get_absolute_url(self) -> str:
        return reverse("result", args=[self.pk])

    def get_role_display(self) -> str:
        from .questions import ROLE_CHOICES

        return dict(ROLE_CHOICES).get(self.role, self.role)

    @property
    def category_scores(self) -> list[tuple[str, int]]:
        scores = self.report.get("scores", {})
        return [(LABELS[key], scores[key]) for key in LABELS if key in scores]
