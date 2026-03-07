# Cough Weakness Detection System

A comprehensive audio analysis system for detecting and monitoring cough weakness in patients with respiratory conditions.

## Architecture

The system is built in four modular steps:

### 1. **detect.py** - Cough Detection
Isolates individual cough segments from raw audio using:
- Amplitude envelope extraction (rolling RMS window)
- Dynamic thresholding (3x median amplitude)
- Duration filtering (100-800ms per segment)

**Output**: List of cough start/end sample indices

### 2. **features.py** - Feature Extraction
Extracts 6 clinically-relevant features from each cough:

1. **Peak-to-decay ratio**: Energy in first half / second half (strength indicator)
2. **Spectral centroid**: Frequency-weighted center of spectrum (turbulence)
3. **Spectral slope**: Rate of high-frequency energy drop-off (weakness indicator)
4. **Rise time**: Time to peak amplitude in milliseconds (expulsive force)
5. **Zero-crossing rate**: Number of sign changes (airflow turbulence)
6. **Expulsive duration**: Time above 50% peak amplitude (sustained force)

**Output**: Averaged features + per-cough details with standard deviation

### 3. **scoring.py** - Severity & Confidence Scoring
Four-part scoring system:

#### Step 4: Baseline Comparison
- Compares current features to patient's stored baseline
- Computes percent change for each feature

#### Step 5: Severity Scoring (0-100)
- Weighted deviation model:
  - Spectral centroid: 25%
  - Peak-to-decay ratio: 25%
  - Rise time: 15%
  - Spectral slope: 15%
  - Expulsive duration: 10%
  - Zero-crossing rate: 10%

#### Step 6: Confidence Scoring (0.0-1.0)
Penalties for:
- Only 1 cough detected: -0.2
- High feature variance: -0.15
- Edge-case segment durations: -0.1

#### Step 7: Trend Analysis
- **Declining**: 15+ point increase vs. recent average
- **Sustained decline**: 3+ consecutive severity increases
- **Flags**: Clinical thresholds, medication effects

### 4. **analyse.py** - Main Entry Point
Orchestrates the full pipeline and outputs JSON results.

```bash
python analyse.py <audio_path> <patient_id> [medication_status]
```

## Project Structure

```
cough_weakness/
├── detect.py                      # Cough detection
├── features.py                    # Feature extraction
├── scoring.py                     # Severity/confidence scoring
├── analyse.py                     # Main entry point
├── create_test_audio.py          # Synthetic test data generation
├── create_baselines.py           # Baseline feature extraction
├── test_trends.py                # Trend detection testing
├── audio/                        # Audio files
│   ├── patient_001.wav          # Healthy (strong coughs)
│   ├── patient_002.wav          # Moderate decline (medium coughs)
│   └── patient_003.wav          # Severe (weak coughs)
├── baselines/                    # Stored baseline features
│   ├── patient_001.json
│   ├── patient_002.json
│   └── patient_003.json
├── output/                       # Analysis results
│   ├── patient_001_result.json
│   ├── patient_002_result.json
│   └── patient_003_result.json
├── history/                      # Longitudinal severity tracking
│   ├── patient_001_history.json
│   ├── patient_002_history.json
│   └── patient_003_history.json
└── venv/                         # Python virtual environment
```

## Output Format

Each analysis generates a JSON result:

```json
{
  "patient_id": "001",
  "timestamp": "2026-03-06T21:32:32.679966",
  "status": "success",
  "num_coughs": 3,
  "features": {
    "spectral_centroid": 5010.95,
    "peak_to_decay_ratio": 0.93,
    "spectral_slope": -0.0000824,
    "rise_time": 95.62,
    "zero_crossing_rate": 0.296,
    "expulsive_duration": 24.46
  },
  "severity": 10.0,
  "confidence": 0.85,
  "trend": "stable",
  "flags": [],
  "medication_status": null
}
```

## Usage

### Quick Start (with synthetic test data)

```bash
# Generate synthetic test audio
python create_test_audio.py

# Create baselines from test audio
python create_baselines.py

# Analyze a recording
python analyse.py audio/patient_001.wav 001

# Test trend detection
python test_trends.py
```

### With Real Audio

Audio files can be in **WAV or OPUS** format (or any format supported by librosa).

1. Place audio file in `audio/` directory
2. Create patient baseline:
   ```python
   from detect import detect_coughs
   from features import extract_features
   import librosa
   import json

   y, sr = librosa.load("audio/my_audio.wav")
   coughs = detect_coughs("audio/my_audio.wav")
   features = extract_features(y, coughs)

   with open("baselines/patient_XXX.json", "w") as f:
       json.dump(features["averaged"], f)
   ```

3. Run analysis (works with .wav or .opus):
   ```bash
   python analyse.py audio/my_audio.wav XXX on
   # or
   python analyse.py audio/my_audio.opus XXX on
   ```

## Test Results

The synthetic test patients show expected behavior:

- **Patient 001** (healthy): High-energy coughs, low severity (10.0)
- **Patient 002** (moderate): Medium-energy coughs, moderate severity (20.5)
- **Patient 003** (severe): Weak, breathless coughs, high severity (varies)

Trend detection monitors longitudinal changes and flags concerning patterns.

## Audio Format Support

The system supports **multiple audio formats**:
- **WAV** (PCM, uncompressed)
- **OPUS** (compressed, ~1/10th file size)
- Any format supported by librosa + audioread (MP3, FLAC, etc.)

**Note on OPUS**: Opus requires specific sample rates (8000, 12000, 16000, 24000, 48000 Hz). The system automatically handles resampling via librosa.

## Dependencies

- librosa (audio processing)
- scipy (signal processing)
- numpy (numerical computation)
- soundfile (optional, for OPUS format support)

## Integration

Output JSONs are ready for:
- Dashboard visualization
- Clinical decision support
- Longitudinal patient monitoring
- Research data analysis

The system can integrate with EMR systems, mobile health platforms, or standalone web dashboards via the JSON output format.
