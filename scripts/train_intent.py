"""Fine-tune MuRIL on training data; select checkpoints on validation only."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ["weather", "navigation", "hvac", "media", "unknown"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        parser.error("epochs and batch-size must be positive")

    from datasets import load_dataset
    from sklearn.metrics import accuracy_score, f1_score
    from transformers import (
        AutoModelForSequenceClassification, BertTokenizer,
        DataCollatorWithPadding, Trainer, TrainingArguments, set_seed,
    )

    set_seed(42)
    model_name = "google/muril-base-cased"
    label2id = {label: index for index, label in enumerate(LABELS)}
    id2label = {index: label for label, index in label2id.items()}
    data = load_dataset("csv", data_files={
        split: str(ROOT / "data" / "processed" / f"{split}.csv")
        for split in ("train", "validation")
    })
    tokenizer = BertTokenizer.from_pretrained(model_name)

    def tokenize(batch):
        encoded = tokenizer(batch["text"], truncation=True, max_length=64)
        encoded["labels"] = [label2id[label] for label in batch["intent"]]
        return encoded

    encoded = data.map(tokenize, batched=True, remove_columns=data["train"].column_names)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=len(LABELS), label2id=label2id, id2label=id2label,
    )

    def metrics(prediction):
        predicted = prediction.predictions.argmax(axis=-1)
        return {
            "accuracy": accuracy_score(prediction.label_ids, predicted),
            "macro_f1": f1_score(prediction.label_ids, predicted,
                                 labels=list(range(len(LABELS))), average="macro", zero_division=0),
        }

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(ROOT / "models" / "checkpoints"),
            learning_rate=2e-5,
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=args.batch_size,
            num_train_epochs=args.epochs,
            weight_decay=0.01,
            eval_strategy="epoch",
            save_strategy="epoch",
            logging_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="macro_f1",
            greater_is_better=True,
            save_total_limit=2,
            report_to="none",
            seed=42,
            use_cpu=args.cpu,
            dataloader_pin_memory=not args.cpu,
        ),
        train_dataset=encoded["train"],
        eval_dataset=encoded["validation"],
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics=metrics,
    )
    trainer.train()
    destination = ROOT / "models" / "intent-muril"
    trainer.save_model(str(destination))
    tokenizer.save_pretrained(str(destination))
    validation = trainer.evaluate()
    training = trainer.evaluate(encoded["train"], metric_key_prefix="train")
    (destination / "validation_metrics.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8",
    )
    (destination / "training_metrics.json").write_text(
        json.dumps(training, indent=2), encoding="utf-8",
    )
    print(f"Saved model and tokenizer to {destination}")
    print("Validation results only. The test split was not loaded.")


if __name__ == "__main__":
    main()
