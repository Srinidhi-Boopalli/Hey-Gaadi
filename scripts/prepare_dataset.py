"""Validate the starter CSV and split by semantic family, using only Python."""
import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LABELS = {"weather", "navigation", "hvac", "media", "unknown"}
FIELDS = ["sample_id", "text", "intent", "language", "group_id", "split", "source"]


def prepare() -> None:
    rows = []
    for filename in ("seed.csv", "training_expansion.csv"):
        with (ROOT / "data" / filename).open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != FIELDS:
                raise ValueError(f"Expected columns: {FIELDS}")
            incoming = list(reader)
            if filename == "training_expansion.csv" and any(
                row["split"] != "train" for row in incoming
            ):
                raise ValueError("Expansion rows must belong to training only")
            rows.extend(incoming)

    seen_ids, seen_text = set(), set()
    groups = {}
    for row in rows:
        if any(not row[field].strip() for field in FIELDS):
            raise ValueError(f"Missing value: {row}")
        if row["intent"] not in LABELS or row["split"] not in {"train", "validation", "test"}:
            raise ValueError(f"Invalid label or split: {row}")
        key = " ".join(row["text"].casefold().split())
        if row["sample_id"] in seen_ids or key in seen_text:
            raise ValueError(f"Duplicate ID or text: {row}")
        seen_ids.add(row["sample_id"])
        seen_text.add(key)
        group_value = (row["intent"], row["split"])
        if groups.setdefault(row["group_id"], group_value) != group_value:
            raise ValueError(f"Group crosses labels or splits: {row['group_id']}")

    for split in ("train", "validation", "test"):
        subset = [row for row in rows if row["split"] == split]
        if {row["intent"] for row in subset} != LABELS:
            raise ValueError(f"Split {split} must contain every label")

    # Write only after all validation has succeeded.
    destination = ROOT / "data" / "processed"
    destination.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation", "test"):
        subset = [row for row in rows if row["split"] == split]
        with (destination / f"{split}.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(subset)
        print(f"{split}: {len(subset)} samples; labels={dict(Counter(row['intent'] for row in subset))}")


if __name__ == "__main__":
    prepare()
