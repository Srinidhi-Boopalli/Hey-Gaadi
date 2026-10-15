"""Configuration stays on the server; API keys never go to the browser."""
import os
import math
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    # A deliberately small .env reader: KEY=value, optional surrounding quotes.
    # Existing process variables win. Shell expansion is intentionally absent.
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip().replace("_", "").isalnum():
            raise ValueError("Invalid .env entry; use KEY=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Settings:
    intent_backend: str = "rules"
    asr_backend: str = "disabled"
    slot_backend: str = "rules"
    weather_backend: str = "demo"
    maps_backend: str = "links"
    tts_backend: str = "browser"
    min_score: float = 0.70
    groq_model: str = "openai/gpt-oss-20b"
    sarvam_stt_model: str = "saaras:v3"
    sarvam_tts_model: str = "bulbul:v3"
    parakeet_model: str = "nvidia/parakeet-tdt-0.6b-v3"
    groq_key: str = field(default="", repr=False)
    sarvam_key: str = field(default="", repr=False)
    weather_key: str = field(default="", repr=False)
    maps_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls):
        load_env()
        settings = cls(
            intent_backend=os.getenv("INTENT_BACKEND", "rules"),
            asr_backend=os.getenv("ASR_BACKEND", "disabled"),
            slot_backend=os.getenv("SLOT_BACKEND", "rules"),
            weather_backend=os.getenv("WEATHER_BACKEND", "demo"),
            maps_backend=os.getenv("MAPS_BACKEND", "links"),
            tts_backend=os.getenv("TTS_BACKEND", "browser"),
            min_score=float(os.getenv("INTENT_MIN_SCORE", "0.70")),
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            sarvam_stt_model=os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
            sarvam_tts_model=os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
            parakeet_model=os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3"),
            groq_key=os.getenv("GROQ_API_KEY", ""),
            sarvam_key=os.getenv("SARVAM_API_KEY", ""),
            weather_key=os.getenv("OPENWEATHER_API_KEY", ""),
            maps_key=os.getenv("GOOGLE_MAPS_API_KEY", ""),
        )
        choices = {
            "intent_backend": {"rules", "muril"},
            "asr_backend": {"disabled", "whisper", "sarvam", "parakeet"},
            "slot_backend": {"rules", "groq"},
            "weather_backend": {"demo", "openweather"},
            "maps_backend": {"links", "google"},
            "tts_backend": {"browser", "sarvam"},
        }
        for name, allowed in choices.items():
            if getattr(settings, name) not in allowed:
                raise ValueError(f"Invalid {name}; choose from {sorted(allowed)}")
        if not math.isfinite(settings.min_score) or not 0 <= settings.min_score <= 1:
            raise ValueError("INTENT_MIN_SCORE must be between 0 and 1")
        needs = [
            (settings.slot_backend == "groq", settings.groq_key, "GROQ_API_KEY"),
            (settings.asr_backend == "sarvam" or settings.tts_backend == "sarvam", settings.sarvam_key, "SARVAM_API_KEY"),
            (settings.weather_backend == "openweather", settings.weather_key, "OPENWEATHER_API_KEY"),
            (settings.maps_backend == "google", settings.maps_key, "GOOGLE_MAPS_API_KEY"),
        ]
        for enabled, key, name in needs:
            if enabled and not key:
                raise ValueError(f"Selected provider requires {name}")
        return settings
