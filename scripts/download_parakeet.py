"""Optional English benchmark model; requires NeMo and significant disk/RAM."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from nemo.collections.asr.models import ASRModel
    from app.config import Settings
    settings = Settings.from_env()
    model = ASRModel.from_pretrained(settings.parakeet_model)
    destination = ROOT / "models" / "parakeet.nemo"
    destination.parent.mkdir(parents=True, exist_ok=True)
    model.save_to(str(destination))
    print(f"Saved checkpoint to {destination}")


if __name__ == "__main__":
    main()
