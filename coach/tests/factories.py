from coach.analysis.posture import PostureReport
from coach.analysis.speech import SpeechMetrics


def make_speech(**overrides) -> SpeechMetrics:
    values = dict(
        syllables=120,
        pauses=6,
        speech_rate=3.6,
        articulation_rate=4.4,
        speaking_duration=26.0,
        total_duration=33.0,
        balance=0.79,
        f0_mean=140.0,
        f0_std=28.0,
        f0_median=136.0,
        f0_min=85.0,
        f0_max=260.0,
        f0_q25=120.0,
        f0_q75=155.0,
        pronunciation_prob=0.92,
    )
    values.update(overrides)
    return SpeechMetrics(**values)


def make_posture(good_ratio=0.9, issue_ratios=None, frames=20) -> PostureReport:
    return PostureReport(
        frames_analysed=frames,
        frames_with_person=frames,
        good_ratio=good_ratio,
        issue_ratios=issue_ratios or {},
    )
