"""Black-box local API check against a running rule-mode demo server."""
import argparse
import io
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    import httpx
    with httpx.Client(base_url=args.url, timeout=180) as client:
        health = client.get("/health"); health.raise_for_status()
        if health.json()["intent_backend"] != "rules" or health.json()["slot_backend"] != "rules":
            parser.error("Run smoke check with INTENT_BACKEND=rules SLOT_BACKEND=rules")
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.post("/commands", json={"text": "   "}).status_code == 422
        result = client.post("/commands", json={"text": "AC on karo"}); result.raise_for_status()
        assert result.headers.get("x-request-id")
        identifier = result.json()["session_id"]
        assert result.json()["state"]["ac_on"]
        result = client.post("/commands", json={"text": "set cabin temperature to 22", "session_id": identifier}).json()
        assert result["state"]["temperature"] == 22
        assert client.post("/commands", json={"text": "AC on mat karo", "session_id": identifier}).json()["action"] is None
        assert client.delete(f"/sessions/{identifier}").status_code == 200
        assert client.get(f"/sessions/{identifier}").json()["state"]["ac_on"] is False
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as file:
            file.setnchannels(1); file.setsampwidth(2); file.setframerate(16000); file.writeframes(b"\x00\x00" * 16000)
        response = client.post("/voice", files={"file": ("silence.wav", buffer.getvalue(), "audio/wav")})
        expected = 503 if health.json()["asr_backend"] == "disabled" else 422
        assert response.status_code == expected, response.text
        assert client.get("/metrics").json()["requests"] > 0
    print("Black-box API checks passed: static UI, validation, session state, reset, request IDs, voice rejection, metrics.")


if __name__ == "__main__":
    main()
