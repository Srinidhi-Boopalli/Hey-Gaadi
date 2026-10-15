"""Download the multilingual faster-whisper small checkpoint for local use."""
from pathlib import Path


def main() -> None:
    from huggingface_hub import snapshot_download

    directory = Path(__file__).resolve().parents[1] / "models" / "asr-small"
    snapshot_download(repo_id="Systran/faster-whisper-small", local_dir=directory)
    print(f"Downloaded ASR model to {directory}")


if __name__ == "__main__":
    main()
