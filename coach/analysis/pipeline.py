"""End-to-end analysis of a recorded interview answer."""

from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .media import extract_audio, extract_frames
from .posture import analyse_posture
from .scoring import score_interview
from .speech import analyse_speech

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    report: dict  # scores + tips
    speech: dict
    posture: dict
    snapshot_path: Path | None
    duration_s: float


def analyse_recording(video_path: Path, snapshot_path: Path | None = None) -> AnalysisResult:
    """Decode a browser recording, analyse speech and posture, and score it.

    Intermediate files (WAV, frames, TextGrids) live in a temporary
    directory that is removed when analysis finishes.
    """
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="poise-") as tmp:
        workdir = Path(tmp)

        wav = extract_audio(video_path, workdir / "audio.wav")
        speech = analyse_speech(wav)

        frames = extract_frames(video_path, workdir / "frames", fps=1.0)
        posture = analyse_posture(frames, snapshot_path=snapshot_path) if frames else None

    report = score_interview(speech, posture)
    elapsed = time.monotonic() - started
    logger.info("Analysed %s in %.1fs (score %s)", video_path.name, elapsed, report["overall"])

    return AnalysisResult(
        report=report,
        speech=speech.to_dict(),
        posture=posture.to_dict() if posture else {},
        snapshot_path=Path(posture.snapshot) if posture and posture.snapshot else None,
        duration_s=speech.total_duration,
    )
