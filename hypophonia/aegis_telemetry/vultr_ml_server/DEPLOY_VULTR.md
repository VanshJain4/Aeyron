# Deploy on Vultr (low disk)

The default `torch` package pulls CUDA and fills small disks. Use CPU-only PyTorch.

On the server (after SCP or clone):

```bash
# Free space (remove partial pip install and cache)
pip3 cache purge
rm -rf /root/.cache/pip

# Install PyTorch CPU-only first (~200MB instead of ~2GB)
pip3 install torch --index-url https://download.pytorch.org/whl/cpu

# Then the rest (no torch in requirements.txt)
cd /root/hypophonia/aegis_telemetry/vultr_ml_server
pip3 install -r requirements.txt

# Run
uvicorn server:app --host 0.0.0.0 --port 8000
```

Open port 8000: `ufw allow 8000/tcp && ufw --force enable`
