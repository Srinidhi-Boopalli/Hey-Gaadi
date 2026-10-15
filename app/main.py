"""Hey Gaadi local application: UI, REST API, speech, and provider boundaries."""
import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.asr import build_transcriber
from app.config import ROOT, Settings
from app.engine import Engine
from app.providers import ProviderError, Providers
from app.schemas import CommandRequest, CommandResponse, SpeechRequest, VoiceResponse
from app.speech import MAX_BYTES, validate_wav

logger = logging.getLogger("hey_gaadi")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uvicorn's default access log includes query strings; use sanitized metadata.
    logging.getLogger("uvicorn.access").disabled = True
    settings = Settings.from_env()
    providers = Providers(settings)
    try:
        classifier = None
        if settings.intent_backend == "muril":
            from app.model_intents import MurilClassifier
            classifier = MurilClassifier(ROOT / "models" / "intent-muril")
        app.state.settings = settings
        app.state.providers = providers
        app.state.engine = Engine(settings, providers, classifier)
        app.state.transcriber = build_transcriber(settings, providers)
        app.state.asr_lock = threading.Lock()
        app.state.metrics_lock = threading.Lock()
        app.state.metrics = {"requests": 0, "errors": 0, "total_request_ms": 0.0}
        yield
    finally:
        providers.close()
        app.state.transcriber = None
        app.state.engine = None


app = FastAPI(title="Hey Gaadi", version="1.0.0", lifespan=lifespan,
              description="Local multilingual voice prototype. Vehicle actions are simulated.")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")


@app.middleware("http")
async def request_metadata(request: Request, call_next):
    identifier = str(uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        logger.error("Unhandled application error: %s", type(error).__name__)
        response = JSONResponse(status_code=500, content={"detail": "Internal application error; check the server terminal"})
    duration = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = identifier
    response.headers["X-Content-Type-Options"] = "nosniff"
    if hasattr(request.app.state, "metrics"):
        with request.app.state.metrics_lock:
            stats = request.app.state.metrics
            stats["requests"] += 1
            stats["errors"] += int(response.status_code >= 400)
            stats["total_request_ms"] += duration
    logger.info("request=%s method=%s path=%s status=%s ms=%.1f", identifier,
                request.method, request.url.path, response.status_code, duration)
    return response


@app.exception_handler(ProviderError)
async def provider_error(request, error):
    return JSONResponse(status_code=502, content={"detail": str(error)})


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/health")
def health(request: Request):
    settings = request.app.state.settings
    return {"status": "ok", "version": "1.0.0", "intent_backend": settings.intent_backend,
            "asr_backend": settings.asr_backend, "slot_backend": settings.slot_backend,
            "weather_backend": settings.weather_backend, "maps_backend": settings.maps_backend,
            "tts_backend": settings.tts_backend, "vehicle_mode": "simulation"}


@app.get("/metrics")
def metrics(request: Request):
    with request.app.state.metrics_lock:
        stats = dict(request.app.state.metrics)
    count = stats["requests"]
    return {**stats, "mean_request_ms": round(stats["total_request_ms"] / count, 2) if count else 0}


@app.post("/commands", response_model=CommandResponse)
def receive_command(command: CommandRequest, request: Request):
    try:
        return request.app.state.engine.execute(command)
    except ValueError as error:
        raise HTTPException(503, str(error)) from error


@app.get("/sessions/{session_id}")
def get_session(session_id: UUID, request: Request):
    try:
        identifier, session = request.app.state.engine.sessions.get(session_id)
    except ValueError as error:
        raise HTTPException(503, str(error)) from error
    with session.lock:
        return {"session_id": identifier, "state": session.state.model_copy(), "pending": session.pending}


@app.delete("/sessions/{session_id}")
def reset_session(session_id: UUID, request: Request):
    try:
        request.app.state.engine.sessions.reset(session_id)
    except ValueError as error:
        raise HTTPException(503, str(error)) from error
    return {"status": "reset"}


@app.post("/voice", response_model=VoiceResponse)
def receive_voice(request: Request, file: UploadFile, language: Literal["en", "hi"] | None = None,
                  session_id: UUID | None = None, origin: str | None = None):
    transcriber = request.app.state.transcriber
    if transcriber is None:
        raise HTTPException(503, "Speech recognition is disabled; set ASR_BACKEND=whisper or sarvam.")
    if origin is not None and not 1 <= len(origin.strip()) <= 160:
        raise HTTPException(422, "Origin must contain 1 to 160 characters")
    payload = file.file.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise HTTPException(413, "Audio must be at most 2 MiB")
    try:
        duration = validate_wav(payload)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if not request.app.state.asr_lock.acquire(blocking=False):
        raise HTTPException(503, "Speech recognition is busy; retry shortly")
    started = time.perf_counter()
    try:
        transcript, detected = transcriber.transcribe(payload, language)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except ProviderError:
        raise
    except Exception as error:
        logger.error("ASR inference failed: %s", type(error).__name__)
        raise HTTPException(502, "Speech recognition failed; check the model and runtime in the server terminal") from error
    finally:
        request.app.state.asr_lock.release()
    elapsed = (time.perf_counter() - started) * 1000
    if not transcript.strip():
        raise HTTPException(422, "No speech detected; try a clearer recording")
    if len(transcript) > 500:
        raise HTTPException(422, "Transcript exceeds the 500-character command limit")
    command = receive_command(CommandRequest(text=transcript, session_id=session_id,
                                             language=language or (detected if detected in {"en", "hi"} else "en"),
                                             origin=origin), request)
    return VoiceResponse(asr_backend=request.app.state.settings.asr_backend, language=detected,
                         audio_seconds=duration, asr_ms=round(elapsed, 2), command=command)


@app.post("/speech")
def speak(command: SpeechRequest, request: Request):
    if request.app.state.settings.tts_backend != "sarvam":
        raise HTTPException(503, "Server TTS is disabled; the dashboard can use browser speech")
    audio = request.app.state.providers.speak(command.text, command.language)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
