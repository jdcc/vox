"""Audio capture using sounddevice."""

import logging
import queue
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16
BLOCK_SIZE = 1024


class AudioRecorder:
    """Records audio from the microphone."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        """Initialize the audio recorder.

        Args:
            sample_rate: Sample rate for recording (default 16kHz for Whisper)
            on_level: Optional callback for audio level updates
        """
        self.sample_rate = sample_rate
        self.channels = CHANNELS
        self.is_recording = False
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._on_level = on_level
        self._last_level_time = 0.0
        self._level_interval = 1 / 30

    def _calculate_level(self, indata: np.ndarray) -> float:
        samples = indata.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(samples))))
        return rms  # Return raw RMS, let consumer handle scaling

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: dict,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback for audio stream.

        Args:
            indata: Input audio data
            frames: Number of frames
            time_info: Timing information
            status: Stream status flags
        """
        if status:
            logger.warning(f"Audio callback status: {status}")

        if self.is_recording:
            self._audio_queue.put(indata.copy())
            if self._on_level:
                now = time.monotonic()
                if now - self._last_level_time >= self._level_interval:
                    self._last_level_time = now
                    try:
                        self._on_level(self._calculate_level(indata))
                    except Exception as exc:
                        logger.debug(f"Audio level callback failed: {exc}")

    def start_recording(self) -> None:
        """Start recording audio."""
        with self._lock:
            if self.is_recording:
                return

            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

            self.is_recording = True

            if self._stream is None:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=DTYPE,
                    blocksize=BLOCK_SIZE,
                    callback=self._audio_callback,
                )
                self._stream.start()

            logger.debug("Recording started")

    def stop_recording(self) -> bytes:
        """Stop recording and return the recorded audio.

        Returns:
            Raw PCM audio bytes (int16, mono, 16kHz)
        """
        with self._lock:
            if not self.is_recording:
                return b""

            self.is_recording = False

            chunks = []
            while not self._audio_queue.empty():
                try:
                    chunks.append(self._audio_queue.get_nowait())
                except queue.Empty:
                    break

            if not chunks:
                logger.warning("No audio recorded")
                return b""

            audio_data = np.concatenate(chunks, axis=0)
            audio_bytes = audio_data.tobytes()

            logger.debug(f"Recording stopped, {len(audio_bytes)} bytes captured")
            return audio_bytes

    def close(self) -> None:
        """Close the audio stream."""
        with self._lock:
            self.is_recording = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

    def __enter__(self) -> "AudioRecorder":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def list_audio_devices() -> list[dict]:
    """List available audio input devices.

    Returns:
        List of device info dicts
    """
    devices = []
    for i, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            devices.append({
                "index": i,
                "name": device["name"],
                "channels": device["max_input_channels"],
                "sample_rate": device["default_samplerate"],
            })
    return devices


def get_default_input_device() -> dict | None:
    """Get the default input device.

    Returns:
        Device info dict or None
    """
    try:
        device_id = sd.default.device[0]
        if device_id is not None:
            device = sd.query_devices(device_id)
            return {
                "index": device_id,
                "name": device["name"],
                "channels": device["max_input_channels"],
                "sample_rate": device["default_samplerate"],
            }
    except Exception as e:
        logger.error(f"Error getting default device: {e}")

    return None
