"""Benchmark real recordings with WER/CER, latency, and downstream intent accuracy."""
import argparse
import csv
import json
import statistics
import sys
import time
import unicodedata
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LABELS = {"weather", "navigation", "hvac", "media", "unknown"}


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(" " if unicodedata.category(char).startswith("P") else char
                            for char in text).split())


def edit_distance(reference, predicted):
    previous = list(range(len(predicted) + 1))
    for index, token in enumerate(reference, 1):
        current = [index]
        for other, value in enumerate(predicted, 1):
            current.append(min(current[-1] + 1, previous[other] + 1,
                               previous[other - 1] + (token != value)))
        previous = current
    return previous[-1]


def load_manifest(path):
    from app.speech import validate_wav
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        required = {"sample_id", "audio_path", "transcript", "intent", "language", "speaker_id", "condition"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Manifest needs columns {sorted(required)}")
        rows = list(reader)
    if not rows:
        raise ValueError("Manifest contains no recordings")
    identifiers = set()
    for row in rows:
        if any(not row[name].strip() for name in required):
            raise ValueError("Every required manifest cell must be filled")
        if row["sample_id"] in identifiers or row["intent"] not in LABELS or row["language"] not in {"en", "hi"}:
            raise ValueError(f"Invalid/duplicate sample: {row['sample_id']}")
        identifiers.add(row["sample_id"])
        audio = (path.parent / row["audio_path"]).resolve()
        row["resolved_path"] = str(audio)
        row["audio_seconds"] = validate_wav(audio.read_bytes())
    return rows


def summarize(rows):
    successful = [row for row in rows if row["status"] == "ok"]
    if not successful:
        return {"total": len(rows), "successful": 0, "errors": sum(row["status"] == "error" for row in rows),
                "skipped": sum(row["status"] == "skipped" for row in rows)}
    milliseconds = sorted(row["latency_ms"] for row in successful)
    import math
    return {
        "total": len(rows), "successful": len(successful),
        "errors": sum(row["status"] == "error" for row in rows),
        "skipped": sum(row["status"] == "skipped" for row in rows),
        "word_error_rate": sum(row["word_errors"] for row in successful) / sum(row["reference_words"] for row in successful),
        "character_error_rate": sum(row["character_errors"] for row in successful) / sum(row["reference_characters"] for row in successful),
        "intent_accuracy": sum(row["predicted_intent"] == row["intent"] for row in successful) / len(successful),
        "median_latency_ms": statistics.median(milliseconds),
        "p95_latency_ms": milliseconds[math.ceil(len(milliseconds) * .95) - 1],
        "real_time_factor": sum(row["latency_ms"] for row in successful) / (1000 * sum(row["audio_seconds"] for row in successful)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--providers", default="whisper", help="Comma-separated whisper,sarvam,parakeet")
    parser.add_argument("--intent-backend", choices=["rules", "muril"], default="rules")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "asr")
    args = parser.parse_args()
    rows = load_manifest(args.manifest.resolve())
    print(f"Validated {len(rows)} recordings")
    if args.validate_only:
        return
    from app.asr import build_transcriber
    from app.config import Settings
    from app.intents import detect_intent
    from app.providers import Providers
    settings = Settings.from_env()
    names = list(dict.fromkeys(args.providers.split(",")))
    if any(name not in {"whisper", "sarvam", "parakeet"} for name in names):
        parser.error("Unknown provider")
    if "sarvam" in names and not settings.sarvam_key:
        parser.error("Sarvam benchmarking requires SARVAM_API_KEY and uploads audio to Sarvam")
    classifier = None
    if args.intent_backend == "muril":
        from app.model_intents import MurilClassifier
        classifier = MurilClassifier(ROOT / "models" / "intent-muril")
    providers = Providers(settings)
    output, report = [], {"intent_backend": args.intent_backend,
                          "normalization": "NFKC, casefold, punctuation to spaces; CER excludes spaces",
                          "notes": "First sample includes warmup. Compare identical successful recordings and language subsets. WER may exceed 1. Scores use successful samples only; inspect errors/coverage.",
                          "providers": {}}
    try:
        for name in names:
            started = time.perf_counter()
            transcriber = build_transcriber(replace(settings, asr_backend=name), providers)
            load_ms = (time.perf_counter() - started) * 1000
            results = []
            for row in rows:
                item = {key: value for key, value in row.items() if key != "resolved_path"}
                item.update(provider=name, predicted_text="", predicted_intent="", status="ok", error="")
                if name == "parakeet" and row["language"] != "en":
                    item.update(status="skipped", error="Adapter supports English evaluation only")
                else:
                    try:
                        started = time.perf_counter()
                        text, _ = transcriber.transcribe(Path(row["resolved_path"]).read_bytes(), row["language"])
                        item["latency_ms"] = (time.perf_counter() - started) * 1000
                        reference, predicted = normalize(row["transcript"]), normalize(text)
                        ref_words, pred_words = reference.split(), predicted.split()
                        ref_chars, pred_chars = reference.replace(" ", ""), predicted.replace(" ", "")
                        if not ref_words or not ref_chars:
                            raise ValueError("Reference has no normalized content")
                        item.update(predicted_text=text, word_errors=edit_distance(ref_words, pred_words),
                                    reference_words=len(ref_words), character_errors=edit_distance(ref_chars, pred_chars),
                                    reference_characters=len(ref_chars),
                                    predicted_intent=classifier.predict(text)[0] if classifier else detect_intent(text).name)
                    except Exception as error:
                        # Record exception type, not possibly sensitive provider request text.
                        item.update(status="error", error=type(error).__name__)
                output.append(item); results.append(item)
                print(f"{name}: {row['sample_id']} -> {item['status']}")
            report["providers"][name] = {"load_ms": load_ms, "overall": summarize(results),
                "by_language": {language: summarize([row for row in results if row["language"] == language])
                                for language in sorted({row["language"] for row in results})},
                "by_condition": {condition: summarize([row for row in results if row["condition"] == condition])
                                 for condition in sorted({row["condition"] for row in results})}}
            del transcriber
    finally:
        providers.close()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fields = sorted({key for row in output for key in row})
    with (args.output / "predictions.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields); writer.writeheader(); writer.writerows(output)
    print(f"Saved reports to {args.output}")


if __name__ == "__main__":
    main()
