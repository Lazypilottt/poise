"""Helpers for decoding browser recordings with ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from django.conf import settings


class MediaDecodeError(RuntimeError):
    """Raised when ffmpeg can't decode the uploaded recording."""


def _ffmpeg(*args: str, timeout: int = 300) -> None:
    command = [settings.FFMPEG_BINARY, "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise MediaDecodeError(
            f"ffmpeg not found ({settings.FFMPEG_BINARY!r}). Install it or set FFMPEG_BINARY."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaDecodeError("Timed out while decoding the recording.") from exc
    if result.returncode != 0:
        raise MediaDecodeError(result.stderr.strip() or "ffmpeg failed to decode the recording.")


def extract_audio(video_path: Path, wav_path: Path) -> Path:
    """Extract a mono 16-bit WAV track suitable for Praat."""
    _ffmpeg("-i", str(video_path), "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(wav_path))
    return wav_path


def extract_frames(video_path: Path, output_dir: Path, fps: float = 1.0) -> list[Path]:
    """Sample frames from the video at ``fps`` frames per second.

    ffmpeg is used instead of OpenCV because WebM files produced by
    ``MediaRecorder`` usually carry no reliable frame-rate/duration metadata.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-i", str(video_path), "-an", "-vf", f"fps={fps}", "-q:v", "3", str(output_dir / "frame_%04d.jpg"))
    return sorted(output_dir.glob("frame_*.jpg"))
