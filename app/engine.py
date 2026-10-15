"""Orchestrates understanding, validation, provider calls, and simulated state."""
import re
import time

from app.parsing import has, parse_command
from app.providers import ProviderError
from app.schemas import CommandRequest, CommandResponse, ParsedCommand
from app.sessions import SessionStore


class Engine:
    def __init__(self, settings, providers, classifier=None):
        self.settings, self.providers, self.classifier = settings, providers, classifier
        self.sessions = SessionStore()

    def execute(self, request: CommandRequest) -> CommandResponse:
        started = time.perf_counter()
        identifier, session = self.sessions.get(request.session_id)
        text = request.text
        normalized = text.casefold().strip(" .?!।")
        score = None
        with session.lock:
            parsed = parse_command(text)
            def answer(status, action, english, hindi, data=None):
                return CommandResponse(
                    transcript=text, session_id=identifier, intent=parsed.intent,
                    backend=self.settings.intent_backend, score=score, status=status,
                    action=action, reply=hindi if request.language == "hi" else english,
                    language=request.language, state=session.state.model_copy(deep=True),
                    data=data or {}, timings_ms={"command": round((time.perf_counter() - started) * 1000, 2)},
                )

            if normalized in {"cancel", "cancel that", "nevermind", "रद्द करो", "रद्द", "rehne do"}:
                session.pending = None
                return answer("completed", None, "Request cancelled.", "अनुरोध रद्द कर दिया।")

            # Only plain unknown replies fill a pending slot. A new recognized
            # command clears pending context rather than becoming a place name.
            if session.pending and parsed.intent == "unknown" and not parsed.negated:
                slot = session.pending
                if len(text) > 160:
                    return answer("needs_clarification", None, "Please use a shorter place name.", "कृपया जगह का छोटा नाम बताएँ।")
                if slot in {"city", "destination"}:
                    parsed = ParsedCommand(intent="weather" if slot == "city" else "navigation",
                                           operation="current" if slot == "city" else "route",
                                           **{slot: text})
                elif slot in {"temperature", "fan_speed", "volume"} and re.fullmatch(r"-?\d+", normalized):
                    parsed = ParsedCommand(intent="media" if slot == "volume" else "hvac",
                                           operation={"temperature": "set_temperature", "fan_speed": "set_fan",
                                                      "volume": "set_volume"}[slot], **{slot: int(normalized)})
                else:
                    return answer("needs_clarification", None, "Please provide a number, or say cancel.", "कृपया संख्या बताएँ या रद्द कहें।")
                session.pending = None
            else:
                session.pending = None
                if self.classifier and parsed.intent != "ambiguous":
                    label, score = self.classifier.predict(text)
                    if score < self.settings.min_score:
                        parsed.intent = "uncertain"
                        return answer("needs_clarification", None, "Please rephrase your request.", "कृपया अपना अनुरोध दोबारा बताएँ।")
                    parsed.intent = label
                if self.settings.slot_backend == "groq" and parsed.intent not in {"ambiguous", "uncertain"}:
                    try:
                        extracted = self.providers.extract(text, parsed.intent)
                    except ProviderError as error:
                        return answer("provider_error", None, str(error), "भाषा सेवा उपलब्ध नहीं है। फिर कोशिश करें।")
                    # An extractor may reject a command but cannot silently change
                    # an accepted classifier category into a different action.
                    if extracted.intent != parsed.intent and parsed.intent != "unknown":
                        return answer("needs_clarification", None, "Please request one clear action.", "कृपया एक स्पष्ट काम बताएँ।")
                    extracted.negated = extracted.negated or parsed.negated
                    parsed = extracted

            if parsed.negated:
                return answer("needs_clarification", None, "Please state the action you want, without a negative instruction.", "कृपया स्पष्ट बताएँ कि कौन सा काम करना है।")
            if parsed.intent in {"ambiguous", "uncertain"}:
                return answer("needs_clarification", None, "Please request one action at a time.", "कृपया एक समय में एक काम बताएँ।")
            if parsed.intent == "unknown":
                return answer("unsupported", None, "Try weather, navigation, climate, or music.", "मौसम, रास्ता, एसी या संगीत के बारे में पूछें।")

            try:
                if parsed.intent == "weather":
                    if parsed.operation == "forecast":
                        return answer("unsupported", None, "Only current weather is supported; ask for weather now.", "अभी केवल वर्तमान मौसम उपलब्ध है।")
                    if not parsed.city:
                        session.pending = "city"
                        return answer("needs_clarification", None, "Which city?", "कौन सा शहर?")
                    data = self.providers.weather(parsed.city)
                    if data["is_demo"]:
                        return answer("simulated", "weather.current", f"Demo weather for {parsed.city}: 28°C, clear skies. This is sample data.",
                                      f"{parsed.city} का डेमो मौसम: 28 डिग्री, साफ़ आसमान। यह नमूना डेटा है।", data)
                    return answer("completed", "weather.current",
                                  f"{data['city']}: {data['temperature_c']:.0f}°C, {data['description']}.",
                                  f"{data['city']} में तापमान {data['temperature_c']:.0f} डिग्री है। {data['description']}।", data)

                if parsed.intent == "navigation":
                    if not parsed.destination:
                        session.pending = "destination"
                        return answer("needs_clarification", None, "Where would you like to go?", "आप कहाँ जाना चाहते हैं?")
                    if parsed.destination.casefold() in {"home", "office", "ghar", "घर", "my home", "my office"}:
                        return answer("needs_clarification", None, "Please give the full address; saved places aren't configured.", "कृपया पूरा पता बताएँ; घर और ऑफिस के पते सेव नहीं हैं।")
                    data = self.providers.route(parsed.destination, parsed.origin or getattr(request, "origin", None))
                    reply = f"Directions link ready for {parsed.destination}. Open Maps to choose and follow a route."
                    if "distance_km" in data:
                        reply = f"Route to {parsed.destination}: {data['distance_km']:.1f} km, approximately {data['duration_minutes']:.0f} minutes."
                    return answer("completed", "navigation.route", reply,
                                  f"{parsed.destination} का रास्ता तैयार है। नक्शे में रास्ता चुनें।", data)

                if parsed.intent == "hvac":
                    operation = parsed.operation
                    if operation in {"on", "off"}:
                        session.state.ac_on = operation == "on"
                        return answer("simulated", "hvac." + operation,
                                      f"Demo: AC is {operation}.", "डेमो: एसी " + ("चालू है।" if operation == "on" else "बंद है।"))
                    if operation == "set_temperature":
                        if parsed.temperature is None:
                            session.pending = "temperature"
                            return answer("needs_clarification", None, "What temperature, from 16 to 30°C?", "16 से 30 डिग्री के बीच कौन सा तापमान?")
                        if not 16 <= parsed.temperature <= 30:
                            return answer("needs_clarification", None, "Choose a temperature from 16 to 30°C.", "16 से 30 डिग्री के बीच तापमान चुनें।")
                        session.state.temperature = parsed.temperature
                        return answer("simulated", "hvac.set_temperature", f"Demo: temperature set to {parsed.temperature}°C.", f"डेमो: तापमान {parsed.temperature} डिग्री कर दिया।")
                    if operation in {"set_fan", "fan_up", "fan_down"}:
                        speed = parsed.fan_speed
                        if operation != "set_fan":
                            speed = max(0, min(5, session.state.fan_speed + (1 if operation == "fan_up" else -1)))
                        if speed is None:
                            session.pending = "fan_speed"
                            return answer("needs_clarification", None, "Choose fan speed from 0 to 5.", "पंखे की गति 0 से 5 के बीच चुनें।")
                        if not 0 <= speed <= 5:
                            return answer("needs_clarification", None, "Fan speed must be between 0 and 5.", "पंखे की गति 0 से 5 के बीच होनी चाहिए।")
                        session.state.fan_speed = speed
                        return answer("simulated", "hvac.set_fan", f"Demo: fan speed is {speed}.", f"डेमो: पंखे की गति {speed} है।")
                    return answer("needs_clarification", None, "Try AC on/off, set temperature to 22, or set fan speed to 3.", "एसी चालू या बंद करें, तापमान 22 या पंखे की गति 3 बताएँ।")

                if parsed.intent == "media":
                    operation = parsed.operation
                    if operation in {"play", "pause"}:
                        session.state.media_playing = operation == "play"
                    elif operation in {"next", "previous"}:
                        session.state.track = max(1, session.state.track + (1 if operation == "next" else -1))
                    elif operation in {"mute", "unmute"}:
                        session.state.muted = operation == "mute"
                    elif operation == "set_volume":
                        if parsed.volume is None:
                            session.pending = "volume"
                            return answer("needs_clarification", None, "What volume, from 0 to 100?", "आवाज़ 0 से 100 के बीच कितनी रखें?")
                        if not 0 <= parsed.volume <= 100:
                            return answer("needs_clarification", None, "Volume must be between 0 and 100.", "आवाज़ 0 से 100 के बीच होनी चाहिए।")
                        session.state.volume = parsed.volume
                    else:
                        return answer("needs_clarification", None, "Try play music, pause music, next song, or volume 40.", "संगीत बजाओ, गाना रोको, अगला गाना या आवाज़ 40 कहें।")
                    return answer("simulated", "media." + operation,
                                  f"Demo media: {operation.replace('_', ' ')}. Track {session.state.track}, volume {session.state.volume}.",
                                  f"डेमो संगीत अपडेट हुआ। ट्रैक {session.state.track}, आवाज़ {session.state.volume}।")
            except ProviderError as error:
                return answer("provider_error", None, str(error), "सेवा उपलब्ध नहीं है। सेटिंग जाँचें और फिर कोशिश करें।")
            return answer("unsupported", None, "This operation is not supported.", "यह काम अभी उपलब्ध नहीं है।")
