"""Body-language analysis from webcam frames using MediaPipe Pose.

Each sampled frame is scored with a handful of simple, explainable checks
that work for a front-facing webcam:

* shoulder tilt  - the line between the shoulders should be roughly level
* head tilt      - the line between the ears should be roughly level
* slouching      - the nose should sit well above the shoulder line,
                   measured relative to shoulder width so it's scale-free
* looking away   - the nose should sit between the ears horizontally
* framing        - shoulder width relative to the frame tells us whether the
                   candidate is too close to or too far from the camera

The geometry lives in pure functions so it can be unit-tested without
MediaPipe or OpenCV installed.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Thresholds (degrees / ratios). Tuned on laptop-webcam recordings.
MAX_SHOULDER_TILT_DEG = 8.0
MAX_HEAD_TILT_DEG = 12.0
MIN_HEAD_HEIGHT_RATIO = 0.32  # (shoulder_mid_y - nose_y) / shoulder_width
MAX_FACING_OFFSET = 0.30  # |nose_x - ear_mid_x| / ear_width
MAX_FRAME_COVERAGE = 0.85  # shoulder_width / frame_width
MIN_FRAME_COVERAGE = 0.18
MIN_VISIBILITY = 0.5

ISSUE_LABELS = {
    "not_visible": "Not visible in frame",
    "slouching": "Slouching / head dropped",
    "shoulder_tilt": "Uneven shoulders",
    "head_tilt": "Head tilted",
    "looking_away": "Looking away from camera",
    "too_close": "Too close to camera",
    "too_far": "Too far from camera",
}


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    visibility: float = 1.0


@dataclass
class FrameAssessment:
    person_detected: bool
    issues: list[str] = field(default_factory=list)
    shoulder_tilt: float = 0.0
    head_tilt: float = 0.0
    head_height_ratio: float = 0.0
    facing_offset: float = 0.0
    frame_coverage: float = 0.0

    @property
    def is_good(self) -> bool:
        return self.person_detected and not self.issues


def line_tilt_degrees(a: Point, b: Point) -> float:
    """Angle (0-90°) between the line a-b and the horizontal."""
    dx, dy = b.x - a.x, b.y - a.y
    if dx == 0 and dy == 0:
        return 0.0
    angle = abs(math.degrees(math.atan2(dy, dx)))
    return min(angle, 180 - angle)


def assess_frame(landmarks: dict[str, Point] | None, frame_width: float) -> FrameAssessment:
    """Score one frame given pixel-space landmarks.

    ``landmarks`` must contain ``nose``, ``left_shoulder``, ``right_shoulder``,
    ``left_ear`` and ``right_ear``; ``None`` means no person was detected.
    """
    if not landmarks:
        return FrameAssessment(person_detected=False, issues=["not_visible"])

    nose = landmarks["nose"]
    l_sh, r_sh = landmarks["left_shoulder"], landmarks["right_shoulder"]
    l_ear, r_ear = landmarks["left_ear"], landmarks["right_ear"]

    shoulder_width = math.dist((l_sh.x, l_sh.y), (r_sh.x, r_sh.y))
    if shoulder_width < 1 or min(l_sh.visibility, r_sh.visibility, nose.visibility) < MIN_VISIBILITY:
        return FrameAssessment(person_detected=False, issues=["not_visible"])

    shoulder_mid_y = (l_sh.y + r_sh.y) / 2
    ear_width = abs(l_ear.x - r_ear.x)
    ear_mid_x = (l_ear.x + r_ear.x) / 2

    result = FrameAssessment(
        person_detected=True,
        shoulder_tilt=line_tilt_degrees(l_sh, r_sh),
        head_tilt=line_tilt_degrees(l_ear, r_ear),
        head_height_ratio=(shoulder_mid_y - nose.y) / shoulder_width,
        facing_offset=abs(nose.x - ear_mid_x) / ear_width if ear_width > 0 else 1.0,
        frame_coverage=shoulder_width / frame_width if frame_width else 0.0,
    )

    ears_visible = min(l_ear.visibility, r_ear.visibility) >= MIN_VISIBILITY
    if result.head_height_ratio < MIN_HEAD_HEIGHT_RATIO:
        result.issues.append("slouching")
    if result.shoulder_tilt > MAX_SHOULDER_TILT_DEG:
        result.issues.append("shoulder_tilt")
    if ears_visible and result.head_tilt > MAX_HEAD_TILT_DEG:
        result.issues.append("head_tilt")
    if not ears_visible or result.facing_offset > MAX_FACING_OFFSET:
        result.issues.append("looking_away")
    if result.frame_coverage > MAX_FRAME_COVERAGE:
        result.issues.append("too_close")
    elif result.frame_coverage < MIN_FRAME_COVERAGE:
        result.issues.append("too_far")
    return result


@dataclass
class PostureReport:
    frames_analysed: int
    frames_with_person: int
    good_ratio: float  # share of frames with a person and no issues
    issue_ratios: dict[str, float]  # issue -> share of analysed frames
    snapshot: str | None = None  # path of an annotated frame, if saved

    def to_dict(self) -> dict:
        return {
            "frames_analysed": self.frames_analysed,
            "frames_with_person": self.frames_with_person,
            "good_ratio": round(self.good_ratio, 3),
            "issue_ratios": {k: round(v, 3) for k, v in self.issue_ratios.items()},
        }


def summarise(assessments: list[FrameAssessment]) -> PostureReport:
    total = len(assessments)
    if total == 0:
        return PostureReport(0, 0, 0.0, {})
    counts = Counter(issue for a in assessments for issue in a.issues)
    return PostureReport(
        frames_analysed=total,
        frames_with_person=sum(a.person_detected for a in assessments),
        good_ratio=sum(a.is_good for a in assessments) / total,
        issue_ratios={issue: counts[issue] / total for issue in ISSUE_LABELS if counts[issue]},
    )


# --------------------------------------------------------------------------- #
# MediaPipe / OpenCV integration
# --------------------------------------------------------------------------- #

_LANDMARK_NAMES = {
    "nose": "NOSE",
    "left_shoulder": "LEFT_SHOULDER",
    "right_shoulder": "RIGHT_SHOULDER",
    "left_ear": "LEFT_EAR",
    "right_ear": "RIGHT_EAR",
}


def _sample(items: list, limit: int) -> list:
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def _annotate(image, landmarks: dict[str, Point], assessment: FrameAssessment):
    import cv2

    colour = (80, 200, 120) if assessment.is_good else (60, 80, 235)  # BGR
    p = {name: (int(pt.x), int(pt.y)) for name, pt in landmarks.items()}
    for a, b in [
        ("left_shoulder", "right_shoulder"),
        ("left_ear", "right_ear"),
        ("left_shoulder", "left_ear"),
        ("right_shoulder", "right_ear"),
    ]:
        cv2.line(image, p[a], p[b], colour, 3, cv2.LINE_AA)
    mid = ((p["left_shoulder"][0] + p["right_shoulder"][0]) // 2, (p["left_shoulder"][1] + p["right_shoulder"][1]) // 2)
    cv2.line(image, mid, p["nose"], colour, 3, cv2.LINE_AA)
    for point in p.values():
        cv2.circle(image, point, 7, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(image, point, 7, colour, 2, cv2.LINE_AA)

    label = "Good posture" if assessment.is_good else ", ".join(ISSUE_LABELS[i] for i in assessment.issues)
    cv2.rectangle(image, (0, 0), (image.shape[1], 44), (30, 30, 30), -1)
    cv2.putText(image, label, (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2, cv2.LINE_AA)
    return image


def analyse_posture(frame_paths: list[Path], snapshot_path: Path | None = None, max_frames: int = 60) -> PostureReport:
    """Run MediaPipe Pose over sampled frames and summarise body language.

    If ``snapshot_path`` is given, an annotated copy of a representative
    frame (the most common outcome) is written there.
    """
    import cv2
    import mediapipe as mp

    pose_lm = mp.solutions.pose.PoseLandmark
    frames = _sample(sorted(frame_paths), max_frames)
    assessments: list[FrameAssessment] = []
    annotated_candidates = []

    with mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1, min_detection_confidence=0.5) as pose:
        for path in frames:
            image = cv2.imread(str(path))
            if image is None:
                continue
            h, w = image.shape[:2]
            result = pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            landmarks = None
            if result.pose_landmarks:
                lm = result.pose_landmarks.landmark
                landmarks = {
                    name: Point(lm[pose_lm[key]].x * w, lm[pose_lm[key]].y * h, lm[pose_lm[key]].visibility)
                    for name, key in _LANDMARK_NAMES.items()
                }
            assessment = assess_frame(landmarks, w)
            assessments.append(assessment)
            if landmarks and assessment.person_detected:
                annotated_candidates.append((path, landmarks, assessment))

    report = summarise(assessments)

    if snapshot_path and annotated_candidates:
        # Pick a frame that reflects the overall verdict: a good frame if most
        # frames were good, otherwise one showing the most common issue.
        if report.good_ratio >= 0.5:
            pool = [c for c in annotated_candidates if c[2].is_good] or annotated_candidates
        else:
            top_issue = max(report.issue_ratios, key=report.issue_ratios.get, default=None)
            pool = [c for c in annotated_candidates if top_issue in c[2].issues] or annotated_candidates
        path, landmarks, assessment = pool[len(pool) // 2]
        image = _annotate(cv2.imread(str(path)), landmarks, assessment)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(snapshot_path), image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        report.snapshot = str(snapshot_path)

    return report
