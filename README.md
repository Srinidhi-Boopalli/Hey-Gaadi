# Hey Gaadi

A local Hindi/English voice-assistant prototype for learning the complete path
from microphone audio to a useful, inspectable response. Built with Python,
FastAPI, local Whisper ASR, optional fine-tuned MuRIL, and configurable service
adapters. The browser dashboard supports text, push-to-talk, WAV uploads,
spoken replies, simulated climate controls, and local music playback.

**Runs locally with Python or Docker Compose.** Vehicle hardware,
wake-word detection, and continuous full-duplex streaming are not implemented.
This is a working local prototype, not a production-certified in-car system.

## Run locally

Clone the repository and create a Python 3.12 environment:

```bash
git clone https://github.com/Srinidhi-Boopalli/Hey-Gaadi.git
cd Hey-Gaadi
uv venv --python 3.12
```

Install dependencies and start the application:

```bash
uv pip install -r requirements.txt
uv run scripts/download_asr.py
ASR_BACKEND=whisper INTENT_BACKEND=rules SLOT_BACKEND=rules \
  uv run python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/**. The homepage now contains the dashboard;
http://127.0.0.1:8000/docs remains the interactive API console.
If your environment doesn't exist yet, run `uv venv --python 3.12` first.
For a lightweight text-only installation, install requirements-core.txt and
start with ASR_BACKEND=disabled instead. No paid keys are needed in demo mode.
No dependency install, inference, or model download occurs automatically when
opening the dashboard. Local models load during server startup.

Model files already downloaded in this workspace needn't be downloaded again.
Stop an existing server with Ctrl+C before starting another on port 8000.

## Hands-on first run

1. Click **AC on**, then **22° cabin**. Observe the simulated vehicle state.
2. Type `weather`, then answer `Mysuru`. Observe the follow-up city slot.
3. Type `navigate to Mysuru Palace`. Open the generated Maps link if desired.
4. Click the microphone, speak `AC chalu karo`, then click again to send.
5. Select Hindi and try `एसी चालू करो`. Replies switch to Hindi.
6. Add a local music file, then try `play music`, `volume 20`, and `pause music`.
7. Expand **Inspect response** to see intent, status, state, and stage timing.

Microphone permission must be granted by you. The browser records at most 15
seconds and produces the server's WAV format. Availability of Hindi browser
voices depends on your OS. Browser speech may use a network voice. Recordings
are not explicitly persisted by application code, although UploadFile can use
framework-managed temporary spooling. Opening Maps shares locations with Google.

## What's implemented

| Component | Default behavior | Optional integration |
|---|---|---|
| Speech input | Whisper small, CPU/INT8 when enabled | Sarvam STT; English Parakeet/NeMo adapter |
| Intent detection | English/Hindi keyword baseline | Saved MuRIL classifier |
| Parameters | Explicit grammar and slot follow-ups | Groq JSON extraction with local validation |
| Weather | Clearly labeled demo conditions | OpenWeather geocoding + current weather |
| Navigation | Google Maps directions links | Google Routes distance/duration |
| HVAC | Session-based simulated AC, temperature, fan | No real vehicle connection |
| Media | Simulated state plus selected browser music | No account/media-service integration |
| Speech output | Browser speech synthesis | Sarvam WAV synthesis |
| Pipeline | Whole-utterance REST | Optional Pipecat frame-based CLI |
| Evaluation | Dataset checks and intent evaluation | ASR WER/CER, latency, condition breakdowns |
| Packaging | Dockerfile, Compose on localhost:8002, and CI | No public hosting configured |

Recognizing a category doesn't mean every operation in that category is supported.
Forecasts, saved home/office addresses, arbitrary song search, defrost, heater,
and recirculation are not implemented. Invalid/conflicting requests clarify
instead of silently applying another operation. The grammar is intentionally
limited; it isn't universal Hindi/English or multilingual understanding.

## Configuration and live providers

Copy the example only if you want persistent settings:

```bash
cp .env.example .env
```

Edit .env locally. Never paste keys into chat or commit them. This file supports
plain KEY=value and optional surrounding quotes; it doesn't evaluate shell
commands or expand `$VARIABLES`. Process variables take precedence.

| Variable | Values | Required key |
|---|---|---|
| INTENT_BACKEND | rules / muril | Local saved model for muril |
| ASR_BACKEND | disabled / whisper / sarvam / parakeet | SARVAM_API_KEY for sarvam |
| SLOT_BACKEND | rules / groq | GROQ_API_KEY |
| WEATHER_BACKEND | demo / openweather | OPENWEATHER_API_KEY |
| MAPS_BACKEND | links / google | GOOGLE_MAPS_API_KEY |
| TTS_BACKEND | browser / sarvam | SARVAM_API_KEY |

Enable one provider at a time and restart the server. /health and the dashboard
show provider names, never keys. API credentials/billing permissions must be
configured in each provider's account. OpenWeather was verified in the local application. Other cloud adapters require
live verification with your own credentials; contract/error tests use mocks.

OpenWeather receives the city; Google Routes receives origin/destination;
Groq receives command text; Sarvam STT receives audio; Sarvam TTS receives reply
text. Google Routes requires a starting location, which you can enter in the UI.
Providers are never enabled just because a key exists. Demo provider failures
are not silently converted to fictional live success.

Official references: [Sarvam STT](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe),
[Sarvam TTS](https://docs.sarvam.ai/api-reference/text-to-speech/convert),
[Groq JSON outputs](https://console.groq.com/docs/structured-outputs),
[OpenWeather](https://openweathermap.org/api/current),
[Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started),
[Google Routes](https://developers.google.com/maps/documentation/routes/compute_route_directions).

## MuRIL training and evaluation

```bash
uv pip install -r requirements-ml.txt
uv run scripts/prepare_dataset.py
uv run scripts/train_intent.py --epochs 10
uv run scripts/predict_intent.py "AC chalu karo"
uv run scripts/evaluate_intent.py --split validation
```

The current dataset is **150 authored text examples**, not 600 speech recordings:
120 train / 15 validation / 15 test. Related translations stay together. Hindi
phrasing needs human review and representative collected examples. The latest
saved run had 91.7% training accuracy and 100% on the tiny validation split;
these are not production accuracy measurements. The intent test split remains
held out. Evaluate it only after choosing the final model/settings.

To compare model mode locally:

```bash
ASR_BACKEND=whisper INTENT_BACKEND=muril \
  uv run python -m uvicorn app.main:app --reload
```

The 0.70 score threshold is an uncalibrated demo heuristic. Current model scores
can be about 0.22 even when the selected label is correct, so it will ask for
clarification. For simulation comparison only, add INTENT_MIN_SCORE=0. Do not
interpret the softmax score as measured accuracy or choose thresholds using test
results. See [TRAINING.md](TRAINING.md) and [LEARNING_GUIDE.md](LEARNING_GUIDE.md).

## WAV upload and troubleshooting

Uploads must be mono, 16-bit PCM WAV at 16000 Hz, max 30 seconds and 2 MiB.
The microphone button handles this format for you. To convert an existing file
with FFmpeg installed:

```bash
ffmpeg -i Record.mp3 -vn -ac 1 -ar 16000 -c:a pcm_s16le command.wav
uv run scripts/upload_audio.py command.wav --language hi
```

The Python upload script bypasses Snap curl access restrictions and prints the
actual JSON error. A 422 response describes invalid audio, an invalid request,
no speech, or an overly long transcript; inspect its response body. 503 can mean
ASR is disabled/busy. A model/provider error returns a clear failure rather than
an invented action. Silence/noise filtering does not eliminate ASR hallucinations.

## Benchmark real speech

Copy data/speech_manifest.example.csv to data/speech_manifest.csv, replace its
example rows with recordings and exact human-reviewed reference transcripts,
and place relative audio paths under data/audio/. The example recordings do
not exist until you record them. Obtain consent, separate speakers/sessions,
and label quiet/traffic/cabin conditions honestly.

```bash
uv run scripts/benchmark_asr.py --manifest data/speech_manifest.csv --validate-only
uv run scripts/benchmark_asr.py --manifest data/speech_manifest.csv --providers whisper
```

For Sarvam, set SARVAM_API_KEY and explicitly select `--providers whisper,sarvam`.
That uploads the recordings to Sarvam. Reports go to reports/asr/ and include
WER/CER, median/p95 latency, real-time factor, downstream intent accuracy,
language/condition groups, and failures/skips. Loading time is separate; the
first transcription includes warmup. Compare the same successful samples and
language subset for model selection.

For a synthetic white-noise variant:

```bash
uv run scripts/add_noise.py data/audio/command.wav data/audio/command_noise.wav --snr-db 10
```

Use condition `synthetic_white_noise_10db`, not `traffic`. Synthetic noise is not
representative of real horns, road vibration, or overlapping speech. The shipped
asr-smoke report only verifies the pipeline on a public English sample and a
noise variant; it isn't an Indian-road benchmark.

## Optional Pipecat and Parakeet experiments

Keep these dependencies in separate environments; they can change core packages.
Do not install them into a working environment without checking compatibility.

```bash
uv venv --python 3.12 .venv-pipeline
uv pip install --python .venv-pipeline/bin/python -r requirements-core.txt -r requirements-asr.txt -r requirements-pipecat.txt
.venv-pipeline/bin/python scripts/pipecat_demo.py --text "AC on karo"
ASR_BACKEND=whisper .venv-pipeline/bin/python scripts/pipecat_demo.py --audio command.wav --language hi
```

The Pipecat pipeline was checked with text and file audio. It is utterance-level,
not continuous WebRTC/WebSocket streaming. It may download NLTK tokenizer data
on the first run into models/nltk. The default browser app continues using REST.
MuRIL mode additionally needs requirements-ml.txt in that environment.

For the optional English Parakeet benchmark, create a separate Python 3.12 NeMo
environment, install requirements-core.txt, requirements-asr.txt, and
requirements-parakeet.txt there, run scripts/download_parakeet.py, then benchmark
with `--providers parakeet` on English recordings. NeMo may require additional
platform/CUDA dependencies; this adapter was not installed or executed here.
The chosen checkpoint does not cover Hindi. See NVIDIA's model card before
choosing another checkpoint or language.

## Verify the build

```bash
uv run python -m unittest discover -s tests -v
uv run scripts/smoke_api.py
# If Node.js is available:
node tests/test_frontend.js
```

smoke_api.py expects a running rule-mode server. It tests HTTP behavior,
including session state/reset, input validation, voice rejection, metrics, and
request IDs. Tests do not require paid API keys. Core unit tests are offline.
GitHub CI runs core Python and frontend audio checks if this project is later
pushed to a repository. No repository has been published by this build.

## Read the code

```text
app/
  main.py                 HTTP endpoints, model lifecycle, request metrics
  schemas.py              Typed input/output and extracted command fields
  config.py               Environment settings and provider validation
  intents.py              Keyword classifier baseline
  model_intents.py        Saved MuRIL inference
  parsing.py              Supported grammar and parameters
  engine.py               Understanding, follow-ups, bounded actions
  sessions.py             Per-session simulated vehicle state
  providers.py            Groq, OpenWeather, Maps, Sarvam adapters
  speech.py / asr.py       WAV validation and selectable ASR
  pipecat_pipeline.py     Optional frame-based utterance pipeline
  static/                 Dashboard, recorder worklet, WAV encoding
scripts/                  Training, evaluation, downloads, benchmarks, smoke tests
data/                     Text examples and speech manifest schema
models/                   Local artifacts; excluded from Git and Docker image
reports/                  Measured local results; excluded from Git
```

[LEARNING_GUIDE.md](LEARNING_GUIDE.md) walks through every stage, explains choices
and alternatives, and gives hands-on checkpoints.
[DEPLOYMENT_LATER.md](DEPLOYMENT_LATER.md) documents Docker Compose and the
boundary before public hosting. The app is unauthenticated and uses process-local
sessions: keep it on localhost until the necessary deployment controls are added.

## Author

Boopalli Srinidhi · [GitHub](https://github.com/Srinidhi-Boopalli)
