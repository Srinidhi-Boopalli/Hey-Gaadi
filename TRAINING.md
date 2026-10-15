# Step 4: MuRIL training

Use a Python 3.11 or 3.12 environment for the ML workflow. Dependency ranges
target the Transformers 4 API and are not a tested lockfile. PyTorch device
availability depends on your machine and its installed build.

From the project directory, with your environment activated:

```bash
python -m pip install -r requirements-ml.txt
python scripts/prepare_dataset.py
python scripts/train_intent.py
python scripts/predict_intent.py "AC chalu karo"
```

The first training run needs internet to download MuRIL/tokenizer files.
Trainer uses an available supported device; `--cpu` forces CPU execution.
Use `--batch-size 2` if accelerator memory is insufficient. CPU training can
be slow and full fine-tuning needs substantial memory even with small batches.

The classification head starts untrained; newly initialized weight warnings
are expected. Training uses train.csv; checkpoint selection uses validation.csv.
test.csv is deliberately not loaded. The 60-example starter is a workflow demo,
not enough evidence for production performance. No accuracy target is guaranteed.

The saved model and tokenizer are under models/intent-muril. API routing still
uses rules. Run local predictions first, then evaluate on held-out data and
define fallback behavior before integrating the model with the API.

Hyperparameters are initial choices: 3 epochs, 2e-5 learning rate, batch size 4,
64-token truncation, seed 42. Do not lowercase input for this cased checkpoint.
Dynamic padding pads to each batch's longest example. Track truncation if you
expand to longer commands. A fixed seed helps reproducibility but cannot ensure
identical results across devices and library versions.
