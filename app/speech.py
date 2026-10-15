import io
import wave
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 30


def validate_wav(payload: bytes) -> float:
    if len(payload) > MAX_BYTES:
        raise ValueError("Audio must be at most 2 MiB")
    try:
        with wave.open(io.BytesIO(payload), "rb") as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise ValueError("Use mono 16-bit PCM WAV audio")
            if audio.getframerate() != 16000:
                raise ValueError("Use a 16000 Hz sample rate")
            duration = audio.getnframes() / audio.getframerate()
            if not 0 < duration <= MAX_SECONDS:
                raise ValueError("Audio must contain between 0 and 30 seconds")
            if len(audio.readframes(audio.getnframes())) != audio.getnframes() * 2:
                raise ValueError("WAV audio is truncated")
            return duration
    except (wave.Error, EOFError) as error:
        raise ValueError("Upload a valid uncompressed PCM WAV file") from error


class WhisperTranscriber:
    def __init__(self, directory: Path):
        from faster_whisper import WhisperModel

        if not (directory / "model.bin").is_file():
            raise ValueError("Download ASR files with scripts/download_asr.py first")
        self.model = WhisperModel(str(directory), device="cpu", compute_type="int8", cpu_threads=4)

    def transcribe(self, payload: bytes, language: str | None) -> tuple[str, str]:
        import numpy as np

        validate_wav(payload)
        with wave.open(io.BytesIO(payload), "rb") as audio:
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32) / 32768
        if float(np.sqrt(np.mean(samples ** 2))) < 0.0002:
            return "", language or "unknown"
        segments, info = self.model.transcribe(
            samples, language=language, task="transcribe",
            beam_size=5, vad_filter=True, condition_on_previous_text=False,
        )
        # segments is lazy: consuming it actually performs transcription.
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, info.language
