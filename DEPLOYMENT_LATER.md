# Local Docker Compose

Download Whisper before running a voice-enabled container:

```bash
uv run scripts/download_asr.py
cp .env.example .env
sudo docker compose up -d --build
sudo docker compose logs --tail 50 assistant
```

Open http://127.0.0.1:8002/. The host port is 8002 and the container port is
8000. Change only the host side if another application is using that port.
Keep .env local; it is excluded from Git and the image. Don't overwrite an
existing .env containing your settings. Models are mounted read-only rather
than bundled in the image. Update model-file permissions if the container's
unprivileged user cannot read them.

For real weather, set WEATHER_BACKEND=openweather and OPENWEATHER_API_KEY in
.env, then recreate with `sudo docker compose up -d --force-recreate assistant`.
Navigation defaults to MAPS_BACKEND=links; it doesn't call the Routes API.

Useful commands:

```bash
sudo docker compose ps
sudo docker compose logs -f assistant
sudo docker compose stop
sudo docker compose start
sudo docker compose down
```

Local container execution has been exercised during development. This is not
public production hosting. Before exposing it beyond localhost, implement
HTTPS, authentication, user/session authorization, ingress body/rate limits,
provider budget limits, and shared state if using multiple workers. Browser
microphone capture needs localhost or HTTPS. Memory sessions reset on restart.
Pin and test dependencies for the hosting platform before creating a release.
