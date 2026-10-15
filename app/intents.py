import re
from dataclasses import dataclass


# A small baseline vocabulary, not a trained multilingual model.
KEYWORDS = {
    "weather": ("weather", "mausam", "मौसम", "rain", "बारिश", "humidity", "forecast", "outside"),
    "navigation": ("navigate", "navigation", "directions", "rasta", "रास्ता", "route", "take me", "le chalo", "ले चलो", "guide me"),
    "hvac": ("ac", "air conditioning", "fan", "एसी", "पंखा", "pankha", "pankhe", "पंखे", "cabin", "केबिन", "climate", "heater", "defrost"),
    "media": ("music", "song", "songs", "gaana", "gana", "गाना", "संगीत", "gaane", "गाने", "podcast", "radio", "volume", "mute", "unmute", "playlist"),
}


@dataclass(frozen=True)
class IntentResult:
    name: str
    matches: tuple[str, ...] = ()


def contains_phrase(text: str, phrase: str) -> bool:
    # Boundaries prevent "ac" from matching inside "track".
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None


def detect_intent(text: str) -> IntentResult:
    normalized = " ".join(text.casefold().split())
    matches = tuple(
        intent
        for intent, keywords in KEYWORDS.items()
        if any(contains_phrase(normalized, word) for word in keywords)
    )
    if not matches and any(contains_phrase(normalized, word) for word in ("temperature", "तापमान")):
        matches = ("weather",) if re.search(r"temperature\s+(?:in|at|for)\s+", normalized) else ("hvac",)
    if len(matches) == 1:
        return IntentResult(matches[0], matches)
    if len(matches) > 1:
        return IntentResult("ambiguous", matches)
    return IntentResult("unknown")
