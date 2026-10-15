import io
import importlib.util
import json
import unittest
import wave
from dataclasses import replace
from uuid import uuid4

import httpx

from app.config import Settings
from app.engine import Engine
from app.parsing import parse_command
from app.providers import ProviderError, Providers
from app.schemas import CommandRequest
from app.sessions import SessionStore
from app.speech import validate_wav
from scripts.benchmark_asr import edit_distance, normalize, summarize


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.providers = Providers(Settings())
        self.engine = Engine(Settings(), self.providers)
        self.identifier = uuid4()

    def tearDown(self):
        self.providers.close()

    def command(self, text, **kwargs):
        return self.engine.execute(CommandRequest(text=text, session_id=self.identifier, **kwargs))

    def test_session_isolation_and_persistence(self):
        self.command("AC on karo")
        self.command("set cabin temperature to 22")
        result = self.command("increase fan speed")
        self.assertTrue(result.state.ac_on)
        self.assertEqual((result.state.temperature, result.state.fan_speed), (22, 3))
        other = self.engine.execute(CommandRequest(text="hello"))
        self.assertFalse(other.state.ac_on)
        self.assertEqual(other.state.temperature, 24)

    def test_invalid_temperature_does_not_mutate(self):
        for text in ("set cabin temperature to 99", "set temperature to -10"):
            with self.subTest(text=text):
                result = self.command(text)
                self.assertIsNone(result.action)
                self.assertEqual(result.state.temperature, 24)

    def test_negation_and_conflict_do_not_mutate(self):
        for text in ("AC on mat karo", "don't turn on AC", "AC on off", "weather and AC"):
            with self.subTest(text=text):
                result = self.command(text)
                self.assertIsNone(result.action)
                self.assertFalse(result.state.ac_on)

    def test_unknown_and_unsupported_subsystem(self):
        self.assertEqual(self.command("send an email").status, "unsupported")
        self.assertIsNone(self.command("turn heater on").action)

    def test_followup_city_and_destination(self):
        self.assertEqual(self.command("weather").status, "needs_clarification")
        self.assertTrue(self.command("Mysuru").data["is_demo"])
        self.command("navigate")
        route = self.command("Mysuru Palace")
        self.assertEqual(route.intent, "navigation")
        self.assertIn("Mysuru+Palace", route.data["maps_url"])

    def test_pending_new_command_and_cancel(self):
        self.command("weather")
        self.assertEqual(self.command("play music").action, "media.play")
        self.assertEqual(self.command("Mysuru").status, "unsupported")
        self.command("weather")
        self.command("cancel")
        self.assertEqual(self.command("Mysuru").status, "unsupported")

    def test_temperature_followup(self):
        self.command("set cabin temperature")
        self.assertEqual(self.command("22").state.temperature, 22)

    def test_media_ranges_and_controls(self):
        self.command("play music")
        self.command("next song")
        result = self.command("volume 65")
        self.assertEqual((result.state.track, result.state.volume), (2, 65))
        self.assertEqual(self.command("volume 999").state.volume, 65)
        self.assertTrue(self.command("mute music").state.muted)
        self.assertFalse(self.command("unmute music").state.muted)
        self.assertFalse(self.command("pause music").state.media_playing)

    def test_hindi_reply_and_command(self):
        result = self.command("एसी चालू करो", language="hi")
        self.assertEqual(result.action, "hvac.on")
        self.assertIn("डेमो", result.reply)

    def test_forecast_is_not_fabricated(self):
        self.assertEqual(self.command("weather tomorrow").status, "unsupported")

    def test_outside_temperature_and_cabin_are_distinct(self):
        result = self.command("temperature in Chennai")
        self.assertEqual(result.intent, "weather")
        self.assertTrue(result.data["is_demo"])
        self.assertEqual(self.command("set temperature to 22").state.temperature, 22)

    def test_missing_saved_address(self):
        self.assertIsNone(self.command("navigate to home").action)

    def test_low_score_abstains(self):
        class WeakClassifier:
            def predict(self, text):
                return "hvac", .21
        engine = Engine(replace(Settings(), intent_backend="muril"), self.providers, WeakClassifier())
        result = engine.execute(CommandRequest(text="AC on"))
        self.assertEqual(result.intent, "uncertain")
        self.assertIsNone(result.action)
        self.assertFalse(result.state.ac_on)

    def test_provider_failure_has_no_fake_success(self):
        def fail(city):
            raise ProviderError("Weather unavailable")
        self.providers.weather = fail
        result = self.command("weather in Chennai")
        self.assertEqual(result.status, "provider_error")
        self.assertIsNone(result.action)

    def test_reset_session(self):
        self.command("AC on")
        self.engine.sessions.reset(self.identifier)
        self.assertFalse(self.command("hello").state.ac_on)


class ProviderTests(unittest.TestCase):
    def provider(self, settings, handler):
        provider = Providers(settings, httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(provider.close)
        return provider

    def test_weather_contract(self):
        def handler(request):
            self.assertEqual(request.url.params["appid"], "test-only")
            if "/geo/" in request.url.path:
                return httpx.Response(200, json=[{"lat": 12.9, "lon": 77.6}])
            self.assertEqual(request.url.params["units"], "metric")
            return httpx.Response(200, json={"name": "Bengaluru", "main": {"temp": 25}, "weather": [{"description": "cloudy"}], "dt": 1})
        provider = self.provider(replace(Settings(), weather_backend="openweather", weather_key="test-only"), handler)
        result = provider.weather("Bengaluru")
        self.assertFalse(result["is_demo"])
        self.assertEqual(result["temperature_c"], 25)

    def test_routes_contract_and_url_encoding(self):
        def handler(request):
            self.assertEqual(request.headers["x-goog-api-key"], "test-only")
            self.assertEqual(json.loads(request.content)["destination"]["address"], "Mysuru Palace")
            return httpx.Response(200, json={"routes": [{"distanceMeters": 120000, "duration": "7200s"}]})
        provider = self.provider(replace(Settings(), maps_backend="google", maps_key="test-only"), handler)
        result = provider.route("Mysuru Palace", "Bengaluru")
        self.assertEqual((result["distance_km"], result["duration_minutes"]), (120, 120))
        self.assertIn("Mysuru+Palace", result["maps_url"])

    def test_upstream_error_sanitization(self):
        for code in (401, 403, 404, 429, 500):
            with self.subTest(code=code):
                provider = self.provider(Settings(), lambda request: httpx.Response(code, text="secret-upstream-key"))
                with self.assertRaises(ProviderError) as captured:
                    provider.request("Test provider", "GET", "https://example.com")
                self.assertNotIn("secret", str(captured.exception))

    def test_sarvam_stt_contract(self):
        def handler(request):
            self.assertEqual(request.headers["api-subscription-key"], "test-only")
            self.assertIn(b"saaras:v3", request.content)
            return httpx.Response(200, json={"transcript": "एसी चालू करो", "language_code": "hi-IN"})
        provider = self.provider(replace(Settings(), sarvam_key="test-only"), handler)
        self.assertEqual(provider.transcribe_sarvam(b"audio", "hi"), ("एसी चालू करो", "hi"))

    def test_groq_output_is_validated(self):
        provider = self.provider(Settings(), lambda request: httpx.Response(200, json={"choices": [{"message": {"content": '{"intent":"hvac","operation":"shell_command"}'}}]}))
        with self.assertRaises(ProviderError):
            provider.extract("AC on", "hvac")

    def test_sarvam_invalid_audio(self):
        provider = self.provider(replace(Settings(), tts_backend="sarvam"), lambda request: httpx.Response(200, json={"audios": ["invalid base64"]}))
        with self.assertRaises(ProviderError):
            provider.speak("Hello", "en")


class AudioAndMetricsTests(unittest.TestCase):
    def audio(self, channels=1, rate=16000, seconds=1):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as file:
            file.setnchannels(channels); file.setsampwidth(2); file.setframerate(rate)
            file.writeframes(b"\x00\x00" * channels * rate * seconds)
        return buffer.getvalue()

    def test_audio_valid_and_rejected_cases(self):
        self.assertEqual(validate_wav(self.audio()), 1)
        for payload in (b"invalid", self.audio(channels=2), self.audio(rate=8000), self.audio(seconds=31), self.audio()[:-10]):
            with self.subTest(length=len(payload)):
                with self.assertRaises(ValueError):
                    validate_wav(payload)

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "Requires the optional ASR NumPy dependency")
    def test_whisper_receives_decoded_pcm_not_pyav_file(self):
        import numpy as np
        from types import SimpleNamespace
        from app.speech import WhisperTranscriber
        class FakeModel:
            def transcribe(self, samples, **kwargs):
                if not isinstance(samples, np.ndarray) or samples.dtype != np.float32:
                    raise AssertionError("Expected decoded float32 audio")
                return iter([SimpleNamespace(text="AC on")]), SimpleNamespace(language="en")
        transcriber = WhisperTranscriber.__new__(WhisperTranscriber)
        transcriber.model = FakeModel()
        self.assertEqual(transcriber.transcribe(self.audio(), "en"), ("", "en"))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as file:
            file.setnchannels(1); file.setsampwidth(2); file.setframerate(16000)
            file.writeframes(b"\x00\x10" * 16000)
        self.assertEqual(transcriber.transcribe(buffer.getvalue(), "en"), ("AC on", "en"))

    def test_wer_edit_distance(self):
        self.assertEqual(edit_distance(["ac", "on"], ["ac", "off"]), 1)
        self.assertEqual(edit_distance(["ac"], []), 1)
        self.assertEqual(edit_distance([], ["ac", "on"]), 2)

    def test_unicode_normalization(self):
        self.assertEqual(normalize(" AC, ON! "), "ac on")
        self.assertEqual(normalize("एसी चालू करो।"), "एसी चालू करो")

    def test_benchmark_failures_are_reported(self):
        successful = {"status": "ok", "latency_ms": 500, "audio_seconds": 2,
                      "word_errors": 1, "reference_words": 2, "character_errors": 1,
                      "reference_characters": 4, "predicted_intent": "hvac", "intent": "hvac"}
        result = summarize([successful, {"status": "error"}, {"status": "skipped"}])
        self.assertEqual((result["total"], result["successful"], result["errors"], result["skipped"]), (3, 1, 1, 1))
        self.assertEqual(result["word_error_rate"], .5)
        self.assertEqual(result["real_time_factor"], .25)

    def test_session_capacity(self):
        store = SessionStore(max_sessions=1)
        store.get(None)
        with self.assertRaises(ValueError):
            store.get(None)


if __name__ == "__main__":
    unittest.main()
