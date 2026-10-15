"""Selectable ASR adapters shared by API and benchmarks."""
import tempfile
from pathlib import Path
from app.config import ROOT
from app.speech import WhisperTranscriber


class SarvamTranscriber:
    def __init__(self, providers):
        self.providers = providers

    def transcribe(self, payload, language):
        return self.providers.transcribe_sarvam(payload, language)


class ParakeetTranscriber:
    def __init__(self, checkpoint: Path):
        if not checkpoint.is_file():
            raise ValueError("Download the NeMo checkpoint with scripts/download_parakeet.py")
        from nemo.collections.asr.models import ASRModel
        self.model = ASRModel.restore_from(str(checkpoint), map_location="cpu")
        self.model.eval()

    def transcribe(self, payload, language):
        if language not in {None, "en"}:
            raise ValueError("This Parakeet adapter is for English benchmarking; use Whisper or Sarvam for Hindi")
        with tempfile.TemporaryDirectory(prefix="hey-gaadi-asr-") as directory:
            filename = Path(directory) / "audio.wav"
            filename.write_bytes(payload)
            output = self.model.transcribe([str(filename)], batch_size=1)
            item = output[0]
            text = item if isinstance(item, str) else item.text
            return text.strip(), language or "unknown"


def build_transcriber(settings, providers):
    if settings.asr_backend == "disabled":
        return None
    if settings.asr_backend == "whisper":
        return WhisperTranscriber(ROOT / "models" / "asr-small")
    if settings.asr_backend == "sarvam":
        return SarvamTranscriber(providers)
    if settings.asr_backend == "parakeet":
        return ParakeetTranscriber(ROOT / "models" / "parakeet.nemo")
    raise ValueError("Unknown ASR backend")
