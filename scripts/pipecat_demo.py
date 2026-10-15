"""Run the shared assistant engine through an optional Pipecat frame pipeline."""
import argparse
import asyncio
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def run(args):
    nltk_directory = Path(os.environ.get("NLTK_DATA", str(ROOT / "models" / "nltk"))).resolve()
    nltk_directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NLTK_DATA", str(nltk_directory))
    import nltk
    try:
        nltk.data.find("tokenizers/punkt_tab", paths=[str(nltk_directory)])
    except LookupError:
        if not nltk.download("punkt_tab", download_dir=str(nltk_directory), quiet=True):
            raise RuntimeError("Download NLTK punkt_tab data before running the optional pipeline")
    from app.asr import build_transcriber
    from app.config import Settings
    from app.engine import Engine
    from app.pipecat_pipeline import run_utterance
    from app.providers import Providers
    from app.speech import validate_wav
    settings = Settings.from_env()
    providers = Providers(settings)
    try:
        classifier = None
        if settings.intent_backend == "muril":
            from app.model_intents import MurilClassifier
            classifier = MurilClassifier(ROOT / "models" / "intent-muril")
        engine = Engine(settings, providers, classifier)
        transcriber = build_transcriber(settings, providers) if args.audio else None
        audio = args.audio.read_bytes() if args.audio else None
        if audio is not None:
            validate_wav(audio)
        result = await run_utterance(engine, transcriber, text=args.text or "", language=args.language, audio=audio)
        print(result.model_dump_json(indent=2))
    finally:
        providers.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--audio", type=Path)
    parser.add_argument("--language", choices=["en", "hi"], default="en")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
