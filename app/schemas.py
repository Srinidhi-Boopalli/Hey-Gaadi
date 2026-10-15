from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Intent = Literal["weather", "navigation", "hvac", "media", "unknown", "ambiguous", "uncertain"]


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)
    session_id: UUID | None = None
    language: Literal["en", "hi"] = "en"
    origin: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Command must contain text")
        return value


class ParsedCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent = "unknown"
    operation: Literal["on", "off", "set_temperature", "set_fan", "fan_up", "fan_down",
                       "play", "pause", "next", "previous", "set_volume", "mute", "unmute",
                       "current", "forecast", "route"] | None = None
    city: str | None = Field(default=None, min_length=1, max_length=160)
    destination: str | None = Field(default=None, min_length=1, max_length=160)
    origin: str | None = Field(default=None, min_length=1, max_length=160)
    temperature: int | None = None
    fan_speed: int | None = None
    volume: int | None = None
    negated: bool = False


class VehicleState(BaseModel):
    ac_on: bool = False
    temperature: int = 24
    fan_speed: int = 2
    media_playing: bool = False
    track: int = 1
    volume: int = 40
    muted: bool = False


class CommandResponse(BaseModel):
    transcript: str
    session_id: UUID
    intent: Intent
    backend: str
    score: float | None
    status: Literal["simulated", "completed", "needs_clarification", "unsupported", "provider_error"]
    action: str | None
    reply: str
    language: str
    state: VehicleState
    data: dict = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class VoiceResponse(BaseModel):
    asr_backend: str
    language: str
    audio_seconds: float
    asr_ms: float
    command: CommandResponse


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "hi"] = "en"

    @field_validator("text")
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Speech text must not be blank")
        return value
