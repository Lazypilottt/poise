"""Prosodic speech analysis using Praat (via Parselmouth).

The bundled Praat script detects syllable nuclei from intensity peaks and
voiced segments, then reports timing, pitch and pronunciation statistics.
It is run exactly once per recording and every value is parsed from that
single run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

PRAAT_SCRIPT = Path(__file__).resolve().parent / "praat" / "myspsolution.praat"

# Parameters passed to the Praat script's form, in order.
SILENCE_THRESHOLD_DB = -20
MIN_DIP_BETWEEN_PEAKS_DB = 2
MIN_PAUSE_DURATION_S = 0.3
MIN_PITCH_HZ = 80
MAX_PITCH_HZ = 400
TIME_STEP_S = 0.01

# Order of the values the Praat script prints.
_FIELDS = (
    "syllables",
    "pauses",
    "speech_rate",
    "articulation_rate",
    "speaking_duration",
    "total_duration",
    "balance",
    "f0_mean",
    "f0_std",
    "f0_median",
    "f0_min",
    "f0_max",
    "f0_q25",
    "f0_q75",
    "pronunciation_prob",
)


class SpeechAnalysisError(RuntimeError):
    """Raised when the audio could not be analysed (e.g. silence or noise)."""


@dataclass(frozen=True)
class SpeechMetrics:
    syllables: int
    pauses: int
    speech_rate: float  # syllables / second over the whole recording
    articulation_rate: float  # syllables / second while actually speaking
    speaking_duration: float  # seconds, pauses excluded
    total_duration: float  # seconds, pauses included
    balance: float  # speaking_duration / total_duration
    f0_mean: float  # Hz
    f0_std: float  # Hz
    f0_median: float
    f0_min: float
    f0_max: float
    f0_q25: float
    f0_q75: float
    pronunciation_prob: float  # 0..1 posterior probability of clear pronunciation

    @property
    def pauses_per_minute(self) -> float:
        minutes = self.total_duration / 60
        return self.pauses / minutes if minutes > 0 else 0.0

    @property
    def pitch_variation(self) -> float:
        """Coefficient of variation of the fundamental frequency (std / mean)."""
        return self.f0_std / self.f0_mean if self.f0_mean > 0 else 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["pauses_per_minute"] = round(self.pauses_per_minute, 2)
        data["pitch_variation"] = round(self.pitch_variation, 3)
        return data


def parse_praat_output(text: str) -> SpeechMetrics:
    """Parse the whitespace-separated values printed by the Praat script."""
    text = str(text)
    if "noisy background" in text.lower():
        raise SpeechAnalysisError(
            "Too much background noise to analyse your speech. "
            "Try a quieter room or move closer to the microphone."
        )
    tokens = text.split()
    if len(tokens) < len(_FIELDS):
        raise SpeechAnalysisError(
            f"Expected {len(_FIELDS)} values from Praat, got {len(tokens)}: {text!r}"
        )
    try:
        values = [float(token) for token in tokens[: len(_FIELDS)]]
    except ValueError as exc:
        raise SpeechAnalysisError(f"Unexpected Praat output: {text!r}") from exc

    data = dict(zip(_FIELDS, values))
    data["syllables"] = int(data["syllables"])
    data["pauses"] = int(data["pauses"])
    return SpeechMetrics(**data)


def analyse_speech(wav_path: str | Path) -> SpeechMetrics:
    """Run the Praat script on a WAV file and return the parsed metrics."""
    from parselmouth.praat import run_file  # heavy import, keep it lazy

    # Praat resolves relative paths against the script's folder, so be explicit.
    wav_path = Path(wav_path).resolve()
    if not wav_path.exists():
        raise FileNotFoundError(wav_path)

    try:
        _, output = run_file(
            str(PRAAT_SCRIPT),
            SILENCE_THRESHOLD_DB,
            MIN_DIP_BETWEEN_PEAKS_DB,
            MIN_PAUSE_DURATION_S,
            # The script only completes with this enabled; the TextGrid it writes
            # lands next to the WAV in the per-request working directory.
            "yes",
            str(wav_path),
            str(wav_path.parent) + "/",
            MIN_PITCH_HZ,
            MAX_PITCH_HZ,
            TIME_STEP_S,
            capture_output=True,
        )
    except Exception as exc:  # Praat raises generic errors on unusable audio
        raise SpeechAnalysisError(
            "Couldn't detect clear speech in the recording. "
            "Check your microphone and try again."
        ) from exc

    metrics = parse_praat_output(output)
    if metrics.syllables == 0 or metrics.speaking_duration <= 0:
        raise SpeechAnalysisError(
            "No speech was detected in the recording. Check your microphone and try again."
        )
    return metrics
