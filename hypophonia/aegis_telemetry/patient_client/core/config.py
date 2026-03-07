"""Single source of truth: Vultr URL and baseline audio path (in code, not portal)."""
from pathlib import Path

# Vultr ML server — same for train, live, and dashboard
VULTR_BASE_URL = "http://140.82.11.174:8000"

# Baseline: all audio in this folder are used for training (e.g. .wav, .mp3)
PATIENT_ID = "default"
UCI_PATIENT_ID = "uci"
UCI_PD_PATIENT_ID = "uci_pd"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BASELINE_DATA_DIR = Path(__file__).resolve().parent / "data"  # core/data
BASELINE_AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".m4a")
