# Hey Gaadi: build walkthrough

This guide follows the actual code. Run the checkpoints locally before our
deployment lesson. We have built a complete local prototype, not a certified
vehicle product. It is a push-to-talk assistant; wake-word detection and
continuous full-duplex audio are not implemented.

## 1. Follow one request

Example: say "एसी चालू करो" with Hindi selected.

1. app/static/recorder-worklet.js collects mono microphone samples.
2. app/static/app.js produces a 16 kHz, 16-bit WAV and POSTs it to /voice.
3. app/main.py validates the file and calls the selected ASR adapter.
4. app/speech.py uses Whisper to produce text. Sarvam is an optional adapter.
5. app/engine.py selects an intent and extracts a supported operation.
6. The session's simulated AC state changes. No CAN bus or vehicle hardware is touched.
7. FastAPI returns the transcript, intent, reply, state, and stage timings.
8. The dashboard updates and speaks the reply through browser speech or Sarvam.

Try that request and open "Inspect response" in the conversation. A response
is evidence of what the system did, not just an assistant-generated sentence.

## 2. Why FastAPI and typed schemas?

schemas.py defines the request/response contracts. text is bounded and stripped;
session IDs are UUIDs; language must be en or hi. Invalid requests return 422.
main.py is the boundary for HTTP, not a place to train models or hold parsing rules.

Flask could implement this. FastAPI gives us typed validation and interactive
docs with less manual wiring. Django's ORM, admin, and authentication machinery
would be useful for a larger account-based product, but we don't yet need them.
See https://fastapi.tiangolo.com/tutorial/body/.

Checkpoint: submit whitespace in /docs. It must fail before changing state.

## 3. Why separate intent, parameters, and actions?

"Set cabin temperature to 22" contains three different facts:

```text
intent       = hvac
operation    = set_temperature
temperature  = 22
```

intents.py is our inspectable keyword baseline. model_intents.py is the trained
MuRIL alternative. parsing.py extracts fields through an explicit English/Hindi
grammar. providers.py can instead use Groq to extract a validated ParsedCommand.
engine.py accepts only supported operations and checks numeric ranges before
mutating state. A valid intent alone is not permission to invent an operation.

Groq uses JSON mode followed by Pydantic validation. JSON mode guarantees JSON
syntax rather than our entire schema; local validation is required. An extractor
disagreement with a known classifier category leads to clarification. Unsupported
fields/operations never become shell commands or arbitrary network destinations.
See https://console.groq.com/docs/structured-outputs.

Why not let an LLM do everything? Deterministic execution is easier to inspect,
test, and bound. Why no LangChain dependency? We have a short, explicit workflow;
direct adapters expose its behavior without another orchestration layer.
LangChain becomes a reasonable comparison if retrieval or a complex tool graph
is actually needed; adding its name alone would not improve this application.

Checkpoint: ask for temperature 99. The state must remain unchanged.

## 4. Sessions and follow-up questions

sessions.py keeps state for each UUID. engine.py uses a session lock so two
commands cannot concurrently overwrite the same state. Sessions expire after
an hour of inactivity and the store is limited to 1000 entries.

Say "weather". The assistant asks "Which city?" and remembers pending=city.
Say "Mysuru" in the same session. It fills the city slot. A recognized new
command clears pending context. "cancel" clears it too. Missing numeric values
can similarly be filled by a number in the next turn.

Browser localStorage remembers the session ID; it does not store conversation
audio or API keys. These IDs are demo identifiers, not authentication tokens.
State is process-local, resets on restart, and is not shared across workers.
Use Redis or a database plus authentication before introducing multiple users
or workers. We deliberately use one worker for this local prototype.

Checkpoint: open a private browser window and compare the climate state.

## 5. The MuRIL model and honest evaluation

data/seed.csv contains 60 authored text examples. training_expansion.csv adds
90 training examples: 150 total, split into 120 train / 15 validation / 15 test.
Related translations share group_id and never cross splits. These are not
speech recordings, and automatic exact deduplication cannot detect every
semantic duplicate.

train_intent.py tokenizes text, fine-tunes a pretrained MuRIL checkpoint, and
chooses the checkpoint using validation macro F1. evaluate_intent.py reports
accuracy, macro F1, class confusion, language results, and rule comparisons.
The API calls model.eval() and torch.inference_mode(); it never trains.
See https://huggingface.co/google/muril-base-cased.

Your saved run reached 91.7% training accuracy and 100% on 15 validation rows.
Those numbers are measured, but they do not justify "91% production accuracy".
Validation has influenced development. Keep test.csv separate until we freeze
the chosen model and settings. A final evaluation needs many more independently
collected, human-reviewed examples and speaker/session separation.

Softmax score is not calibrated confidence. This model can rank the right label
while assigning it only about 0.22. The 0.70 API cutoff is a conservative demo
heuristic and rejects such commands. INTENT_MIN_SCORE=0 lets you observe model
behavior in simulation; it is not a recommended production setting. Select
thresholds using representative validation data and measure coverage versus
accepted-prediction error rate. Never select them on the final test set.

Checkpoint: compare predict_intent.py with the API at thresholds 0 and 0.70.

## 6. ASR and the microphone

Audio is accepted as mono, 16-bit PCM WAV at 16000 Hz, 0-30 seconds, up to 2 MiB.
Browser recordings stop after 15 seconds. The worklet collects samples; JS
resamples when needed and writes a WAV header. An arbitrary renamed MP3 is not
a WAV. The server checks its real header and frame data.

Whisper small is loaded once at startup and runs locally on CPU with INT8.
speech.py decodes accepted WAVs with Python wave and NumPy, avoiding PyAV's
decoder API incompatibility encountered in this environment. VAD filters silence;
a low RMS check rejects essentially silent input. These filters do not guarantee
no hallucinations in noisy recordings. A lock bounds local ASR to one request at
a time; concurrent voice uploads receive 503 instead of creating an unbounded
inference queue. This is a local performance choice, not a scaling architecture.
See https://github.com/SYSTRAN/faster-whisper.

Why not Parakeet for all languages? The selected v3 checkpoint covers European
languages, not Hindi. Our optional adapter is restricted to English benchmarking.
NeMo runs in a separate environment to avoid coupling its dependency constraints
to our main app. Sarvam is an alternative for Indic speech; enabling it sends
audio to Sarvam and needs a key. Neither optional provider has been benchmarked
on real Indian-road recordings here.
See https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 and
https://docs.sarvam.ai/api-reference/speech-to-text/transcribe.

Checkpoint: upload silence, then a spoken command. Inspect the actual 422 body
if validation fails. scripts/upload_audio.py avoids Snap curl's file sandbox.

## 7. Weather and navigation

Weather defaults to a clearly labeled 28°C demo response for the requested city.
With WEATHER_BACKEND=openweather, providers.py first resolves the city through
the geocoding API, then requests current weather with metric units. We do not
pretend to provide forecasts: tomorrow's weather is currently unsupported.
Disambiguate city names with a country if needed; the adapter takes the first
geocoding result. See https://openweathermap.org/api/geocoding-api and
https://openweathermap.org/current.

Navigation defaults to an encoded Google Maps directions link. No API key is
required for links. Opening the link shares locations with Google. The app does
not claim to start turn-by-turn navigation inside this dashboard. Home/office
shortcuts ask for a full address because saved places are not configured.
See https://developers.google.com/maps/documentation/urls/get-started.

With MAPS_BACKEND=google, a server-side Routes API call returns distance and
duration; it requires a configured key and origin. These are route estimates,
not a promise of travel time. We use the current Routes API rather than building
a new integration around the legacy Directions API. See
https://developers.google.com/maps/documentation/routes/compute_route_directions.

Provider calls have bounded timeouts. Bad credentials, rate limits, and invalid
responses produce explicit errors. There is no automatic retry of commands that
could double-apply an action. Keys and raw upstream errors are not sent to UI.

Checkpoint: use demo weather first, then enable one live provider at a time.

## 8. Climate, media, and speech output

The engine bounds temperature to 16-30°C, fan speed to 0-5, and volume to 0-100.
AC on/off, fan adjustments, temperature, playback, next/previous, mute, and volume
are supported. Heater, recirculation, defrost, real hardware control, and arbitrary
media search are not implemented. Unsupported requests ask for clarification.

The dashboard can play music files you explicitly select. They stay in your
browser; changing server-side media state controls the local player. Without
files, playback is a simulator. Track numbers wrap through your selected playlist.
There is no Spotify/YouTube account integration.

Browser speech is the zero-key default, but available Hindi voices depend on
your OS/browser and some voices may use a network service. Sarvam TTS optionally
returns WAV bytes from /speech. It receives reply text and language. The app
does not clone voices. See https://docs.sarvam.ai/api-reference/text-to-speech/convert.

Checkpoint: load a music file, say "play music", then "volume 20" and "pause music".

## 9. Pipecat without hiding what is implemented

app/pipecat_pipeline.py provides an optional utterance-level frame pipeline:

```text
UtteranceFrame → transcription processor → CommandFrame
              → intent/action processor → ResultFrame → collector
```

It runs our same adapters and engine. The optional CLI is tested with text and
file audio. Pipecat is pinned to 0.0.104 for this example; install it in a separate
environment. It is not used by the default REST dashboard. It has no continuous
WebRTC/WebSocket transport, wake-word detector, or barge-in implementation.
Those are separate features to build and benchmark after this local flow works.
See https://github.com/pipecat-ai/pipecat/tree/v0.0.104.

Why REST now? It makes whole-utterance stages observable. Pipecat is useful when
audio frames, interruptions, transport, and timing must run continuously. Do not
describe this project as low-latency full-duplex streaming until we implement and
measure that transport.

## 10. Benchmarking

Use data/speech_manifest.example.csv as a schema, not a real dataset. Record your
own consented examples and fill audio paths, exact transcripts, labels, language,
speaker IDs, and recording conditions. Keep collected evaluation utterances
separate from training speakers/sessions and don't tune on the final test set.

benchmark_asr.py compares whisper, sarvam, and optional English parakeet. It
reports word error rate, character error rate, median/p95 transcription latency,
real-time factor, and downstream intent accuracy. It separates language and
condition groups and reports failures/skips rather than hiding coverage.

WER = word insertions + deletions + substitutions, divided by reference words.
CER uses normalized characters excluding spaces. Normalization uses NFKC,
casefolding, and punctuation-to-space; Hindi script and Romanized Hindi remain
different. WER can exceed 100% with many insertions. Compare identical successful
recordings, and interpret aggregate results carefully if providers cover different
languages. Report latency hardware and whether model loading/warmup was included.

add_noise.py produces seeded white noise at a requested SNR, preserving the
mixture's ratio rather than clipping. Synthetic white noise does not represent
horns, road vibration, overlapping speakers, or cabin acoustics. Label it honestly.

The asr-smoke report uses one public English sample and its synthetic noise
variant to verify the pipeline, not to estimate Indian-road performance.

## 11. Testing and deployment boundary

tests/test_core.py checks state isolation, ranges, negation, follow-ups,
uncertainty rejection, provider failures/contracts, WAV validation, and metrics.
tests/test_frontend.js checks browser WAV encoding and the worklet stop protocol.
scripts/smoke_api.py sends real HTTP requests to a running local server.

The dashboard was exercised in the browser. Local Whisper transcribed an actual
11-second public English sample. Optional paid providers were tested with mocked
responses, not live credentials. NeMo/Parakeet was not installed or run. Docker
files are prepared, but Docker was unavailable here, so the image is not verified.

Docker packages software and system dependencies; it does not create model files,
collect data, fix model accuracy, or authenticate users. compose.yaml binds only
localhost and mounts models read-only. We will learn build, inspect, and run
before choosing hosting together. See DEPLOYMENT_LATER.md.

First hands-on milestone: restart the app, use typed commands, microphone input,
follow-up weather, and a navigation link. Then inspect each stage's output.
