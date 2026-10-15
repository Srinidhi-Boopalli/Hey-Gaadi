# Intent dataset: starter plus training expansion

Current total: 150 authored text examples. seed.csv contains the original 60;
training_expansion.csv adds 90 training-only rows, six new families per label.
The processed split sizes are now 120 training / 15 validation / 15 test.
Validation and test rows are unchanged. Validation has informed development,
so it is not an independent final performance estimate. Test remains held out.
Expansion broadens intent coverage beyond current action handlers: recognizing
an intent does not mean the application can execute every command in that intent.
The statements below about 30/15/15 describe the original seed only.

60 authored text examples: English, Romanized Hindi, and Hindi in Devanagari.
These are synthetic learning examples, not collected speech or ASR transcripts.
Hindi phrasing and labels need human review before training for deployment.

Labels: weather (conditions or forecast), navigation (destination or route),
hvac (cabin climate), media (audio playback), unknown (outside these categories).
Unknown examples do not exhaust unsupported requests.

Each semantic family has three related language variants under one group_id.
All variants stay in one split. There are two training families, one validation
family, and one test family per label: 30/15/15 rows. The small 50/25/25 split is
for learning the workflow; it is not representative production evaluation.
Do not tune rules, training, or hyperparameters against test.csv.

The classifier predicts only an intent. Destination, city, temperature, playback
action, negation, and multiple intents require separate handling. Ambiguous and
multi-intent commands are excluded from this single-label starter dataset.

For a larger dataset: collect consented utterances, human-check labels, track
speaker/session and semantic family, and keep those groups disjoint across
splits. Keep a fixed test set. Deduplication here catches normalized exact
duplicates only; it does not prove absence of semantic leakage.

Keep audio recordings, speaker IDs, transcripts, consent provenance, recording
conditions, and noise metadata in a separate speech manifest when adding ASR.
Never describe this text dataset as 60 speech samples.
