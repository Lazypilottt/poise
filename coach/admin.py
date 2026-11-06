from django.contrib import admin

from .models import InterviewSession


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "level", "status", "overall_score", "created_at")
    list_filter = ("status", "role", "level")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("report", "speech_metrics", "posture_metrics", "created_at")
