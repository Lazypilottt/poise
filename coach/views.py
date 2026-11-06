import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.mail import send_mail
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .analysis.media import MediaDecodeError
from .analysis.speech import SpeechAnalysisError
from .forms import ContactForm, PracticeSetupForm, SignUpForm
from .models import InterviewSession
from .questions import parse_skills, select_questions

logger = logging.getLogger(__name__)

SESSION_KEY = "practice_setup"


def home(request):
    return render(request, "coach/home.html")


def signup(request):
    if request.user.is_authenticated:
        return redirect("setup")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Welcome to Poise, {user.username}!")
        return redirect("setup")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def setup(request):
    initial = request.session.get(SESSION_KEY, {})
    form = PracticeSetupForm(request.POST or None, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        request.session[SESSION_KEY] = {
            "role": data["role"],
            "level": data["level"],
            "skills": data["skills"],
            "question_count": data["question_count"],
            "questions": select_questions(
                data["role"], data["level"], parse_skills(data["skills"]), data["question_count"]
            ),
        }
        return redirect("interview")
    return render(request, "coach/setup.html", {"form": form})


@login_required
def interview(request):
    practice = request.session.get(SESSION_KEY)
    if not practice:
        messages.info(request, "Pick a role first so we can tailor your questions.")
        return redirect("setup")
    return render(request, "coach/interview.html", {"practice": practice})


@login_required
@require_POST
def submit(request):
    practice = request.session.get(SESSION_KEY)
    upload = request.FILES.get("recording")
    if not practice:
        return JsonResponse({"error": "Your practice session expired. Please start again."}, status=400)
    if upload is None:
        return JsonResponse({"error": "No recording was received."}, status=400)
    if upload.size > settings.MAX_RECORDING_BYTES:
        return JsonResponse({"error": "Recording is too large. Keep answers under ~15 minutes."}, status=413)

    session = InterviewSession.objects.create(
        user=request.user,
        role=practice["role"],
        level=practice["level"],
        questions=practice["questions"],
    )

    # Imported here so the web app can start even if the ML stack is missing.
    from .analysis.pipeline import analyse_recording

    workdir = Path(tempfile.mkdtemp(prefix="poise-upload-"))
    try:
        video_path = workdir / f"recording{Path(upload.name).suffix or '.webm'}"
        with video_path.open("wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)

        snapshot_name = f"snapshots/{uuid.uuid4().hex}.jpg"
        result = analyse_recording(video_path, snapshot_path=Path(settings.MEDIA_ROOT) / snapshot_name)
    except (SpeechAnalysisError, MediaDecodeError) as exc:
        session.status = InterviewSession.Status.FAILED
        session.error = str(exc)
        session.save(update_fields=["status", "error"])
        return JsonResponse({"error": str(exc)}, status=422)
    except Exception:
        logger.exception("Analysis failed for session %s", session.pk)
        session.status = InterviewSession.Status.FAILED
        session.error = "Unexpected error during analysis."
        session.save(update_fields=["status", "error"])
        return JsonResponse({"error": "Something went wrong while analysing your recording."}, status=500)
    finally:
        # Raw recordings are never kept - only derived metrics and one snapshot.
        shutil.rmtree(workdir, ignore_errors=True)

    session.status = InterviewSession.Status.COMPLETE
    session.overall_score = result.report["overall"]
    session.report = result.report
    session.speech_metrics = result.speech
    session.posture_metrics = result.posture
    session.duration_seconds = result.duration_s
    if result.snapshot_path:
        session.snapshot.name = snapshot_name
    session.save()
    return JsonResponse({"redirect": session.get_absolute_url()})


@login_required
def result(request, pk):
    session = get_object_or_404(InterviewSession, pk=pk, user=request.user)
    previous = (
        InterviewSession.objects.filter(
            user=request.user, status=InterviewSession.Status.COMPLETE, created_at__lt=session.created_at
        )
        .values_list("overall_score", flat=True)
        .first()
    )
    score_change = None
    if previous is not None and session.overall_score is not None:
        score_change = session.overall_score - previous
    return render(request, "coach/result.html", {"session": session, "score_change": score_change})


@login_required
def snapshot(request, pk):
    """Serve a session's posture snapshot to its owner only."""
    session = get_object_or_404(InterviewSession, pk=pk, user=request.user)
    if not session.snapshot:
        raise Http404("No snapshot for this session.")
    try:
        return FileResponse(session.snapshot.open("rb"), content_type="image/jpeg")
    except FileNotFoundError as exc:
        raise Http404("Snapshot file is missing.") from exc


@login_required
@require_POST
def delete_session(request, pk):
    session = get_object_or_404(InterviewSession, pk=pk, user=request.user)
    if session.snapshot:
        session.snapshot.delete(save=False)
    session.delete()
    messages.success(request, "Session deleted.")
    return redirect("history")


def _trend_points(scores: list[int], width: int = 600, height: int = 160, pad: int = 24) -> list[dict]:
    """SVG coordinates for a score trend (0-100 on the y-axis)."""
    if len(scores) < 2:
        return []
    step = (width - 2 * pad) / (len(scores) - 1)
    points = []
    for i, score in enumerate(scores):
        y = round(pad + (100 - score) / 100 * (height - 2 * pad), 1)
        points.append({"x": round(pad + i * step, 1), "y": y, "label_y": y - 12, "score": score})
    return points


@login_required
def history(request):
    sessions = InterviewSession.objects.filter(user=request.user)
    completed = [s for s in sessions if s.status == InterviewSession.Status.COMPLETE]
    scores = [s.overall_score for s in reversed(completed)]
    context = {
        "sessions": sessions,
        "trend_points": _trend_points(scores[-20:]),
        "best_score": max(scores, default=None),
        "average_score": round(sum(scores) / len(scores)) if scores else None,
        "completed_count": len(completed),
    }
    return render(request, "coach/history.html", context)


@login_required
def account(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password was updated.")
        return redirect("account")
    return render(request, "coach/account.html", {"form": form})


def contact(request):
    initial = {"email": request.user.email, "name": request.user.username} if request.user.is_authenticated else None
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        send_mail(
            subject=f"[Poise] Message from {data['name']}",
            message=f"From: {data['name']} <{data['email']}>\n\n{data['message']}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.CONTACT_EMAIL],
            fail_silently=False,
        )
        messages.success(request, "Thanks! Your message has been sent.")
        return redirect("contact")
    return render(request, "coach/contact.html", {"form": form})
