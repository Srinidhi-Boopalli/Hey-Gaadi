"""Try a saved intent model locally without modifying the API."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text")
    args = parser.parse_args()
    if not args.text.strip():
        parser.error("text must not be blank")
    directory = ROOT / "models" / "intent-muril"
    if not directory.is_dir():
        parser.error("No saved model. Run train_intent.py first.")

    import torch
    from transformers import AutoModelForSequenceClassification, BertTokenizer

    tokenizer = BertTokenizer.from_pretrained(directory, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(directory, local_files_only=True)
    model.eval()
    inputs = tokenizer(args.text, return_tensors="pt", truncation=True, max_length=64)
    with torch.inference_mode():
        probabilities = model(**inputs).logits.softmax(dim=-1)[0]
    index = int(probabilities.argmax().item())
    print(json.dumps({
        "intent": model.config.id2label[index],
        "score": round(float(probabilities[index].item()), 4),
        "label_scores": {
            model.config.id2label[i]: round(float(score.item()), 4)
            for i, score in enumerate(probabilities)
        },
        "note": "Softmax score is not calibrated confidence or measured accuracy.",
    }, indent=2))


if __name__ == "__main__":
    main()
