"""Create a reproducible white-noise variant; never overwrite the source."""
import argparse
import math
import sys
import wave
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--snr-db", type=float, default=10)
    args = parser.parse_args()
    if not math.isfinite(args.snr_db) or not -20 <= args.snr_db <= 60:
        parser.error("SNR must be between -20 and 60 dB")
    if args.input.resolve() == args.output.resolve() or args.output.exists():
        parser.error("Choose a new output path")
    import numpy as np
    from app.speech import validate_wav
    validate_wav(args.input.read_bytes())
    with wave.open(str(args.input), "rb") as file:
        signal = np.frombuffer(file.readframes(file.getnframes()), dtype="<i2").astype(np.float64) / 32768
    power = float(np.mean(signal ** 2))
    if power == 0:
        parser.error("Input is silent")
    noise = np.random.default_rng(42).normal(size=signal.shape)
    noise *= math.sqrt(power / (10 ** (args.snr_db / 10) * float(np.mean(noise ** 2))))
    mixed = signal + noise
    # Scale the entire mixture if needed, preserving SNR instead of clipping.
    mixed /= max(1, float(np.max(np.abs(mixed))) / .99)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(16000)
        file.writeframes((mixed * 32767).astype("<i2").tobytes())
    print(f"Saved synthetic white-noise audio at {args.snr_db} dB SNR; not a real road recording")


if __name__ == "__main__":
    main()
