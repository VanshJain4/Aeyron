# Training on normal vs Parkinson's (hypophonia) voices

Train the baseline on **healthy/normal** voices only. At test time, Parkinson's (hypophonia) voices should get higher MSE and be **flagged**.

## 1. Get a dataset

Public options (check licenses and cite if you use):

- **PC-GITA** – Colombian Spanish, Parkinson's and controls. Often used in speech/PD research. May require a request.
- **mPower** (Synapse) – Mobile app study; includes voice tasks. Create account, request access: [synapse.org](https://www.synapse.org/).
- **Torgo** – Dysarthric (including PD-like) and control speakers. [torgo.readthedocs.io](https://torgo.readthedocs.io/).
- **DaTong** – Chinese PD speech (if useful for your demo).
- **UCI / Kaggle** – Search "Parkinson speech dataset" or "hypophonia dataset" for smaller ready-to-use sets.

You need at least **~1–2 minutes of healthy voice** (many 5 s chunks) to train; more is better.

## 2. Folder layout

Put **only healthy/normal** voice files in one folder, e.g.:

```
/path/to/dataset/
  healthy/          ← use this for training
    speaker1_01.wav
    speaker1_02.wav
    speaker2_01.wav
    ...
  parkinson/        ← use these only for testing (upload in the app)
    pd1_01.wav
    ...
```

All files in the chosen folder should be **.wav** (or .mp3, .flac, .m4a). No subfolders are scanned (flat folder only).

## 3. Train on healthy voices

From `patient_client`:

```bash
# Option A: use default folder core/data/ (copy healthy WAVs there first)
python3 train_baseline.py

# Option B: point at your dataset's healthy folder
python3 train_baseline.py --data_dir /path/to/dataset/healthy
```

Same as before: chunks → 5-dim features → send to Vultr → model learns to reconstruct **healthy** voice. Threshold is 80th percentile of baseline MSE.

## 4. Test

- **Healthy file** (from dataset or new): upload in the app → expect **Normal** (low score).
- **Parkinson / hypophonia file**: upload → expect **Possible hypophonia** (higher score, flagged) if the voice differs enough in the 5 features.

If PD voices are not flagged enough, try adding more healthy variety to the training folder or tightening the threshold (e.g. 75th percentile on the server).

## 5. UCI parkinsons.data (tabular)

The UCI Parkinson CSV has **48 healthy** rows (status=0) and 147 PD rows. We use the 48 healthy for the **UCI baseline** (train with `train_uci_baseline.py`). That is enough to train the 5-dim autoencoder (server needs ≥10 vectors); more healthy rows would give a more stable threshold and better generalization. If you get another tabular dataset with the same 5 columns (Fo, Fhi, Jitter, Shimmer, HNR), you can merge healthy rows and re-run `train_uci_baseline.py --csv merged.csv`.
