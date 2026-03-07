"""
Ring buffer for live mic: background thread records into a fixed buffer;
callers can read the last N seconds for real-time inference.
"""
import threading
import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.float32
CHUNK_SEC = 0.5
CHUNK_SAMPLES = int(CHUNK_SEC * SAMPLE_RATE)


class LiveMicBuffer:
    """Thread-safe ring buffer filled by a background recording thread."""

    def __init__(self, max_seconds: float = 20.0, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._max_samples = int(max_seconds * sample_rate)
        self._buf = np.zeros(self._max_samples, dtype=DTYPE)
        self._write_idx = 0
        self._total_written = 0
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._stream is not None:
            return
        self._stop.clear()

        def record_loop() -> None:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=CHUNK_SAMPLES,
                callback=self._callback,
            ) as stream:
                self._stream = stream
                self._stop.wait()

        self._thread = threading.Thread(target=record_loop, daemon=True)
        self._thread.start()
        for _ in range(50):
            if self._stream is not None:
                break
            time.sleep(0.05)

    def _callback(self, indata, _frames, _time, _status) -> None:
        if _status:
            return
        chunk = indata.squeeze()
        with self._lock:
            n = len(chunk)
            for i in range(n):
                self._buf[self._write_idx] = chunk[i]
                self._write_idx = (self._write_idx + 1) % self._max_samples
            self._total_written += n

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._stream = None

    def get_last_seconds(self, n_seconds: float) -> np.ndarray | None:
        """Return last n_seconds of audio, or None if not enough recorded yet."""
        need = int(n_seconds * self.sample_rate)
        with self._lock:
            if self._total_written < need:
                return None
            start = (self._write_idx - need) % self._max_samples
            if start + need <= self._max_samples:
                return self._buf[start : start + need].copy()
            part1 = self._buf[start:].copy()
            part2 = self._buf[: self._write_idx].copy()
            return np.concatenate([part1, part2])

    def seconds_available(self) -> float:
        with self._lock:
            return min(self._total_written / self.sample_rate, self._max_samples / self.sample_rate)

    def is_running(self) -> bool:
        return self._stream is not None
