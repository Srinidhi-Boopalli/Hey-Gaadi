"""Compare saved MuRIL and keyword rules on a chosen split."""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LABELS = ["weather", "navigation", "hvac", "media", "unknown"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["train", "validation", "test"], default="validation")
    args = parser.parse_args()

    import torch
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
    from transformers import AutoModelForSequenceClassification, BertTokenizer
    from app.intents import detect_intent

    with (ROOT / "data" / "processed" / f"{args.split}.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError("Evaluation split is empty")
    directory = ROOT / "models" / "intent-muril"
    tokenizer = BertTokenizer.from_pretrained(directory, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(directory, local_files_only=True)
    model.eval()
    predictions = []
    for row in rows:
        inputs = tokenizer(row["text"], return_tensors="pt", truncation=True, max_length=64)
        with torch.inference_mode():
            scores = model(**inputs).logits.softmax(dim=-1)[0]
        index = int(scores.argmax().item())
        predictions.append({
            **row,
            "muril_prediction": model.config.id2label[index],
            "muril_score": float(scores[index].item()),
            "rules_prediction": detect_intent(row["text"]).name,
        })

    truth = [row["intent"] for row in rows]
    report = {"split": args.split, "samples": len(rows), "labels": LABELS,
              "warning": "Small synthetic dataset; softmax scores are uncalibrated."}
    for name in ("muril", "rules"):
        predicted = [row[f"{name}_prediction"] for row in predictions]
        matrix_labels = LABELS + ["ambiguous"]
        report[name] = {
            "accuracy": accuracy_score(truth, predicted),
            "macro_f1": f1_score(truth, predicted, labels=LABELS, average="macro", zero_division=0),
            "per_class": classification_report(truth, predicted, labels=LABELS,
                                                output_dict=True, zero_division=0),
            "prediction_counts": dict(Counter(predicted)),
            "confusion_matrix_labels": matrix_labels,
            "confusion_matrix": confusion_matrix(truth, predicted, labels=matrix_labels).tolist(),
            "by_language": {},
        }
        for language in sorted({row["language"] for row in rows}):
            selected = [row for row in predictions if row["language"] == language]
            report[name]["by_language"][language] = {
                "samples": len(selected),
                "accuracy": accuracy_score([row["intent"] for row in selected],
                                           [row[f"{name}_prediction"] for row in selected]),
            }
        print(f"{name}: accuracy={report[name]['accuracy']:.3f}, macro_f1={report[name]['macro_f1']:.3f}")

    destination = ROOT / "reports" / args.split
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (destination / "predictions.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    print(f"Reports saved to {destination}")
    if args.split == "test":
        print("Test set has now been inspected. Do not use its results to tune this model.")


if __name__ == "__main__":
    main()
