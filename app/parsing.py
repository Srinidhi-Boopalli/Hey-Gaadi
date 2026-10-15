"""Explicit English/Hindi command grammar; unsupported operations stay unsupported."""
import re

from app.intents import contains_phrase, detect_intent
from app.schemas import ParsedCommand

NEGATIONS = ("don't", "dont", "not", "mat", "मत", "नहीं")


def has(text: str, *phrases: str) -> bool:
    return any(contains_phrase(text, phrase) for phrase in phrases)


def parse_command(text: str) -> ParsedCommand:
    normalized = " ".join(text.casefold().split()).strip(".!?। ")
    command = ParsedCommand(intent=detect_intent(normalized).name,
                            negated=has(normalized, *NEGATIONS))
    if command.intent in {"unknown", "ambiguous"}:
        return command
    if command.intent == "weather":
        command.operation = "forecast" if has(normalized, "tomorrow", "forecast", "kal", "कल") else "current"
        patterns = [r"(?:weather|temperature|forecast)\s+(?:in|for|at)\s+(.+)",
                    r"(.+?)\s+(?:mein|me|में)\s+(?:mausam|weather|मौसम)",
                    r"(.+?)\s+(?:ka|की|का)\s+(?:mausam|weather|मौसम)"]
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                city = match.group(1).strip(" .?!।")
                city = re.sub(r"\s+(?:today|please|aaj|आज)$", "", city)
                command.city = city[:160]
                break
    elif command.intent == "navigation":
        command.operation = "route"
        patterns = [r"(?:navigate|navigation|directions|take me|guide me|route|go)\s+(?:to\s+)?(.+)",
                    r"(.+?)\s+(?:tak|तक)\s+(?:le|jaane|जाने|ले|ka|का)",
                    r"(?:mujhe|मुझे)\s+(.+?)\s+(?:le chalo|ले चलो)"]
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                destination = re.sub(r"\s+please$", "", match.group(1)).strip()
                if destination not in {"to", "me", "directions", "route"}:
                    command.destination = destination[:160]
                break
    elif command.intent == "hvac":
        # Don't reinterpret unsupported subsystems as the main climate switch.
        if has(normalized, "defrost", "heater", "recirculation", "rear", "डीफ़्रॉस्ट", "हीटर", "पीछे"):
            return command
        if has(normalized, "temperature", "degrees", "degree", "तापमान", "डिग्री"):
            command.operation = "set_temperature"
            numbers = re.findall(r"-?\d+", normalized)
            command.temperature = int(numbers[0]) if len(numbers) == 1 else None
        elif has(normalized, "fan", "pankha", "पंखा", "पंखे", "pankhe"):
            up = has(normalized, "increase", "up", "badhao", "बढ़ाओ")
            down = has(normalized, "decrease", "down", "lower", "kam", "कम")
            numbers = re.findall(r"-?\d+", normalized)
            if up != down:
                command.operation = "fan_up" if up else "fan_down"
            elif not up and len(numbers) == 1:
                command.operation, command.fan_speed = "set_fan", int(numbers[0])
        else:
            on = has(normalized, "on", "chalu", "चालू")
            off = has(normalized, "off", "band", "बंद")
            if on != off:
                command.operation = "on" if on else "off"
    elif command.intent == "media":
        if has(normalized, "volume", "आवाज़", "awaaz"):
            command.operation = "set_volume"
            numbers = re.findall(r"-?\d+", normalized)
            command.volume = int(numbers[0]) if len(numbers) == 1 else None
        else:
            choices = {
                "play": ("play", "bajao", "बजाओ", "chalao", "चलाओ"),
                "pause": ("pause", "stop", "roko", "रोको"),
                "next": ("next", "agla", "अगला"),
                "previous": ("previous", "pichla", "पिछला"),
                "mute": ("mute",), "unmute": ("unmute",),
            }
            matches = [operation for operation, words in choices.items() if has(normalized, *words)]
            command.operation = matches[0] if len(matches) == 1 else None
    return command
