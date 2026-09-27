"""Audio capture using sounddevice."""

import logging
import queue
import threading
from typing import Callable

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16
BLOCK_SIZE = 1024

# Peak amplitude (of a possible 32767) below which captured audio is treated
# as effectively silent - a strong signal that the mic is muted, its gain is
# too low, or the wrong device is selected, rather than the user staying quiet.
SILENT_PEAK_THRESHOLD = 500


class AudioRecorder:
    """Records audio from the microphone."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        device: int | str | None = None,
    ) -> None:
        """Initialize the audio recorder.

        Args:
            sample_rate: Sample rate for recording (default 16kHz for Whisper)
            device: Device index (int), name (str), or None for default
        """
        self.sample_rate = sample_rate
        self.channels = CHANNELS
        self.device = device
        self.is_recording = False
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._capture_rate: float | None = None
        self._lock = threading.Lock()

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

            if self._stream is None:
                self._stream, self._capture_rate = self._open_stream()

            self.is_recording = True
            logger.debug("Recording started")

    def _open_stream(self) -> tuple[sd.InputStream, float]:
        """Open the input stream, falling back to the device's native rate.

        Raw hardware devices (e.g. ALSA hw:X,Y) often reject arbitrary sample
        rates outright, unlike PulseAudio/PipeWire-routed devices which
        resample transparently. Retry at the device's own default rate rather
        than failing outright; stop_recording() resamples back down to
        self.sample_rate afterward.
        """
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=DTYPE,
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
                device=self.device,
            )
            stream.start()
            return stream, self.sample_rate
        except Exception:
            native_rate = self._native_sample_rate()
            if native_rate == self.sample_rate:
                raise

            logger.debug(f"Retrying microphone at its native rate: {native_rate}Hz")
            stream = sd.InputStream(
                samplerate=native_rate,
                channels=self.channels,
                dtype=DTYPE,
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
                device=self.device,
            )
            stream.start()
            return stream, native_rate

    def _native_sample_rate(self) -> float:
        """Look up the configured device's own default sample rate."""
        try:
            return float(sd.query_devices(self.device)["default_samplerate"])
        except Exception:
            return float(self.sample_rate)

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

            if self._capture_rate and self._capture_rate != self.sample_rate:
                audio_data = _resample_pcm16(audio_data, self._capture_rate, self.sample_rate)

            peak = int(np.abs(audio_data).max())
            rms = float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
            logger.info(f"Captured audio: peak={peak}/32767, rms={rms:.1f}")
            if peak < SILENT_PEAK_THRESHOLD:
                logger.warning(
                    f"Captured audio is very quiet (peak amplitude {peak}/32767); "
                    "check that the microphone isn't muted, its gain is too low, "
                    "or the wrong device is selected"
                )

            audio_bytes = audio_data.tobytes()

            logger.debug(f"Recording stopped, {len(audio_bytes)} bytes captured")
            return audio_bytes

    def set_device(self, device: int | str | None) -> None:
        """Point future recordings at a different input device.

        Closes any open stream so the next start_recording() reopens on the
        new device, picking up hardware changes between recordings.

        Args:
            device: Device index (int), name (str), or None for default
        """
        with self._lock:
            if device == self.device:
                return

            self.device = device
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._capture_rate = None
            self.is_recording = False

    def close(self) -> None:
        """Close the audio stream."""
        with self._lock:
            self.is_recording = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._capture_rate = None

    def __enter__(self) -> "AudioRecorder":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def _resample_pcm16(audio: np.ndarray, orig_rate: float, target_rate: int) -> np.ndarray:
    """Resample mono int16 PCM via linear interpolation.

    Args:
        audio: Captured samples, any shape that flattens to one channel
        orig_rate: Sample rate the audio was actually captured at
        target_rate: Desired output sample rate

    Returns:
        Resampled int16 samples
    """
    flat = audio.reshape(-1).astype(np.float32)
    duration = len(flat) / orig_rate
    target_len = max(1, round(duration * target_rate))
    orig_times = np.linspace(0, duration, num=len(flat), endpoint=False)
    target_times = np.linspace(0, duration, num=target_len, endpoint=False)
    resampled = np.interp(target_times, orig_times, flat)
    return np.clip(resampled, -32768, 32767).astype(np.int16)


# Generic ALSA plugin/passthrough aliases (dmix, rate converters, etc.) and
# sound-server meta-devices. These don't represent a distinct physical
# microphone - they're software plumbing that duplicates whatever the real
# device or "system default" already offers, and often report nonsensical
# channel counts (e.g. 128) since they'll adapt to whatever asks.
_ALSA_ALIAS_DEVICE_NAMES = {
    "default", "sysdefault", "dmix", "dsnoop", "front",
    "surround40", "surround51", "surround71", "iec958", "hdmi",
    "samplerate", "speexrate", "lavrate", "speex", "upmix", "vdownmix",
    "pulse", "pipewire", "default source", "default sink",
}


def list_audio_devices() -> list[dict]:
    """List available audio input devices.

    Excludes generic ALSA plugin aliases and, when a sound server (e.g.
    PipeWire/PulseAudio) is actively routing audio, raw ALSA hw:X,Y devices -
    those bypass the server and compete with it for exclusive access to the
    hardware, which can silently fail or capture near-silence.

    Returns:
        List of device info dicts
    """
    hostapis = sd.query_hostapis()
    alsa_hostapi_indices = {i for i, api in enumerate(hostapis) if api["name"] == "ALSA"}
    has_routed_hostapi = any(
        i not in alsa_hostapi_indices and api["devices"] for i, api in enumerate(hostapis)
    )

    devices = []
    for i, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] <= 0:
            continue
        if device["name"].lower() in _ALSA_ALIAS_DEVICE_NAMES:
            continue
        if device["name"].lower().endswith(".monitor"):
            continue
        if (
            has_routed_hostapi
            and device["hostapi"] in alsa_hostapi_indices
            and "(hw:" in device["name"]
        ):
            continue

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
