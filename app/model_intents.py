from pathlib import Path


class MurilClassifier:
    """Load once, predict locally on CPU; no training in the API."""

    def __init__(self, directory: Path):
        import torch
        from transformers import AutoModelForSequenceClassification, BertTokenizer

        self.torch = torch
        self.tokenizer = BertTokenizer.from_pretrained(directory, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(directory, local_files_only=True)
        self.model.eval()
        expected = {"weather", "navigation", "hvac", "media", "unknown"}
        if set(self.model.config.id2label.values()) != expected:
            raise ValueError("Saved model must contain the five Hey Gaadi intent labels")

    def predict(self, text: str) -> tuple[str, float]:
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=64)
        with self.torch.inference_mode():
            scores = self.model(**inputs).logits.softmax(dim=-1)[0]
        index = int(scores.argmax().item())
        return self.model.config.id2label[index], float(scores[index].item())
