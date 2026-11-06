"""Turn raw speech and posture metrics into scores and actionable feedback."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .posture import ISSUE_LABELS, PostureReport
from .speech import SpeechMetrics

WEIGHTS = {
    "pace": 0.20,
    "fluency": 0.20,
    "clarity": 0.20,
    "expressiveness": 0.15,
    "body_language": 0.25,
}

LABELS = {
    "pace": "Pace",
    "fluency": "Fluency",
    "clarity": "Clarity",
    "expressiveness": "Expressiveness",
    "body_language": "Body language",
}


def band(value: float, low: float, ideal_low: float, ideal_high: float, high: float) -> float:
    """Score 100 inside [ideal_low, ideal_high], falling linearly to 0 at low/high."""
    if ideal_low <= value <= ideal_high:
        return 100.0
    if value < ideal_low:
        return 0.0 if value <= low else 100.0 * (value - low) / (ideal_low - low)
    return 0.0 if value >= high else 100.0 * (high - value) / (high - ideal_high)


def grade(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Needs work"


@dataclass
class Tip:
    category: str
    positive: bool
    message: str


def _pace(speech: SpeechMetrics) -> tuple[float, Tip]:
    # ~3.0-4.5 syllables/s is roughly 130-170 words per minute.
    score = band(speech.speech_rate, 1.5, 3.0, 4.5, 6.5)
    if speech.speech_rate < 3.0:
        tip = Tip("pace", False, "You're speaking slowly. Aim for a steady, conversational pace of around 140-160 words per minute.")
    elif speech.speech_rate > 4.5:
        tip = Tip("pace", False, "You're speaking quickly. Slow down slightly and let key points land.")
    else:
        tip = Tip("pace", True, "Your speaking pace is comfortable and easy to follow.")
    return score, tip


def _fluency(speech: SpeechMetrics) -> tuple[float, Tip]:
    balance_score = band(speech.balance, 0.3, 0.65, 1.0, 1.01)
    pause_score = band(speech.pauses_per_minute, -1, 0, 15, 40)
    score = (balance_score + pause_score) / 2
    if pause_score < 70:
        tip = Tip("fluency", False, f"You paused about {speech.pauses_per_minute:.0f} times a minute. Structure answers (e.g. STAR) so you know what comes next.")
    elif balance_score < 70:
        tip = Tip("fluency", False, f"Only {speech.balance:.0%} of the recording was speech. Reduce long silences between thoughts.")
    else:
        tip = Tip("fluency", True, "Your answers flowed well with few long pauses.")
    return score, tip


def _clarity(speech: SpeechMetrics) -> tuple[float, Tip]:
    score = max(0.0, min(100.0, speech.pronunciation_prob * 100))
    if score >= 80:
        tip = Tip("clarity", True, "Your pronunciation was clear.")
    else:
        tip = Tip("clarity", False, "Some words were unclear. Articulate word endings and keep the microphone close.")
    return score, tip


def _expressiveness(speech: SpeechMetrics) -> tuple[float, Tip]:
    cv = speech.pitch_variation
    score = band(cv, 0.03, 0.12, 0.30, 0.6)
    if cv < 0.12:
        tip = Tip("expressiveness", False, "Your tone was fairly flat. Vary your pitch to emphasise key points and sound more engaged.")
    elif cv > 0.30:
        tip = Tip("expressiveness", False, "Your pitch varied a lot. Try a calmer, more even delivery.")
    else:
        tip = Tip("expressiveness", True, "Good vocal variety - you sounded engaged.")
    return score, tip


def _body_language(posture: PostureReport) -> tuple[float, list[Tip]]:
    score = posture.good_ratio * 100
    tips: list[Tip] = []
    advice = {
        "not_visible": "Stay centred in the frame for the whole answer.",
        "slouching": "Sit up straight and keep your head level with the camera.",
        "shoulder_tilt": "Keep your shoulders level - avoid leaning to one side.",
        "head_tilt": "Keep your head upright rather than tilted.",
        "looking_away": "Look at the camera more often - it reads as eye contact.",
        "too_close": "Move back a little so your shoulders fit in the frame.",
        "too_far": "Move closer so the interviewer can see your expressions.",
    }
    for issue, ratio in sorted(posture.issue_ratios.items(), key=lambda kv: -kv[1]):
        if ratio >= 0.2:
            tips.append(Tip("body_language", False, f"{ISSUE_LABELS[issue]} in {ratio:.0%} of frames. {advice[issue]}"))
    if not tips:
        tips.append(Tip("body_language", True, "Great posture - upright, centred and facing the camera."))
    return score, tips


def score_interview(speech: SpeechMetrics, posture: PostureReport | None) -> dict:
    """Return overall score, per-category scores and feedback tips."""
    scores: dict[str, float] = {}
    tips: list[Tip] = []

    for key, fn in (("pace", _pace), ("fluency", _fluency), ("clarity", _clarity), ("expressiveness", _expressiveness)):
        scores[key], tip = fn(speech)
        tips.append(tip)

    if posture and posture.frames_analysed:
        scores["body_language"], posture_tips = _body_language(posture)
        tips.extend(posture_tips)

    total_weight = sum(WEIGHTS[k] for k in scores)
    overall = sum(scores[k] * WEIGHTS[k] for k in scores) / total_weight

    return {
        "overall": round(overall),
        "grade": grade(overall),
        "scores": {k: round(v) for k, v in scores.items()},
        "tips": [asdict(t) for t in sorted(tips, key=lambda t: t.positive)],
    }
