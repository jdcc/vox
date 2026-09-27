"""Tests for vox.client.audio."""

import logging
import queue
from unittest.mock import MagicMock

import numpy as np
import pytest

from vox.client import audio as audio_module
from vox.client.audio import AudioRecorder


def test_start_recording_initializes_stream(mock_sounddevice) -> None:
    recorder = AudioRecorder()

    recorder.start_recording()

    assert recorder.is_recording is True
    mock_sounddevice.InputStream.assert_called_once()
    mock_sounddevice.InputStream.return_value.start.assert_called_once()


def test_start_recording_stream_open_failure(mock_sounddevice) -> None:
    mock_sounddevice.InputStream.side_effect = RuntimeError("device unavailable")
    recorder = AudioRecorder()

    try:
        recorder.start_recording()
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    assert recorder.is_recording is False
    assert recorder._stream is None


def test_start_recording_falls_back_to_native_rate(mock_sounddevice) -> None:
    mock_sounddevice.InputStream.side_effect = [RuntimeError("invalid sample rate"), MagicMock()]
    mock_sounddevice.query_devices.return_value = {"default_samplerate": 44100.0}
    recorder = AudioRecorder(device=0)

    recorder.start_recording()

    assert recorder.is_recording is True
    assert recorder._capture_rate == 44100.0
    assert mock_sounddevice.InputStream.call_count == 2


def test_start_recording_fallback_short_circuits_when_rate_matches(mock_sounddevice) -> None:
    mock_sounddevice.InputStream.side_effect = RuntimeError("nope")
    mock_sounddevice.query_devices.return_value = {"default_samplerate": 16000.0}
    recorder = AudioRecorder(device=0)

    with pytest.raises(RuntimeError):
        recorder.start_recording()

    assert recorder.is_recording is False
    assert mock_sounddevice.InputStream.call_count == 1


def test_start_recording_fallback_open_also_raises(mock_sounddevice) -> None:
    mock_sounddevice.InputStream.side_effect = RuntimeError("still broken")
    mock_sounddevice.query_devices.return_value = {"default_samplerate": 44100.0}
    recorder = AudioRecorder(device=0)

    with pytest.raises(RuntimeError):
        recorder.start_recording()

    assert recorder.is_recording is False
    assert recorder._stream is None
    assert mock_sounddevice.InputStream.call_count == 2


def test_start_recording_already_recording(mock_sounddevice) -> None:
    recorder = AudioRecorder()
    recorder.is_recording = True
    recorder._stream = MagicMock()

    recorder.start_recording()

    mock_sounddevice.InputStream.assert_not_called()


def test_start_recording_reuses_stream(mock_sounddevice) -> None:
    recorder = AudioRecorder()
    recorder._stream = MagicMock()

    recorder.start_recording()

    mock_sounddevice.InputStream.assert_not_called()


def test_start_recording_clears_queue_empty() -> None:
    class StubQueue:
        def __init__(self):
            self.calls = 0

        def empty(self):
            self.calls += 1
            return self.calls > 1

        def get_nowait(self):
            raise queue.Empty

    recorder = AudioRecorder()
    recorder._audio_queue = StubQueue()

    recorder.start_recording()


def test_set_device_same_device_is_noop(mock_sounddevice) -> None:
    recorder = AudioRecorder(device=2)
    recorder._stream = MagicMock()

    recorder.set_device(2)

    assert recorder._stream is not None


def test_set_device_closes_open_stream(mock_sounddevice) -> None:
    recorder = AudioRecorder(device=2)
    stream = MagicMock()
    recorder._stream = stream
    recorder.is_recording = True

    recorder.set_device(5)

    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    assert recorder._stream is None
    assert recorder.is_recording is False
    assert recorder.device == 5


def test_set_device_without_open_stream(mock_sounddevice) -> None:
    recorder = AudioRecorder(device=None)

    recorder.set_device(1)

    assert recorder.device == 1
    assert recorder._stream is None


def test_stop_recording_not_recording() -> None:
    recorder = AudioRecorder()

    assert recorder.stop_recording() == b""


def test_stop_recording_with_chunks() -> None:
    recorder = AudioRecorder()
    recorder.is_recording = True
    recorder._audio_queue.put(np.zeros((10, 1), dtype=np.int16))
    recorder._audio_queue.put(np.ones((5, 1), dtype=np.int16))

    data = recorder.stop_recording()

    assert data
    assert len(data) == (15 * 2)


def test_stop_recording_resamples_when_capture_rate_differs() -> None:
    recorder = AudioRecorder()
    recorder.is_recording = True
    recorder._capture_rate = 44100.0
    # 4410 frames @ 44100Hz (0.1s) should resample to 1600 frames @ 16000Hz.
    recorder._audio_queue.put(np.zeros((4410, 1), dtype=np.int16))

    data = recorder.stop_recording()

    assert len(data) == 1600 * 2


def test_stop_recording_warns_when_silent(caplog) -> None:
    recorder = AudioRecorder()
    recorder.is_recording = True
    recorder._audio_queue.put(np.zeros((10, 1), dtype=np.int16))

    with caplog.at_level(logging.WARNING, logger="vox.client.audio"):
        recorder.stop_recording()

    assert any("very quiet" in message for message in caplog.messages)


def test_stop_recording_does_not_warn_when_loud(caplog) -> None:
    recorder = AudioRecorder()
    recorder.is_recording = True
    recorder._audio_queue.put(np.full((10, 1), 10000, dtype=np.int16))

    with caplog.at_level(logging.WARNING, logger="vox.client.audio"):
        recorder.stop_recording()

    assert not any("very quiet" in message for message in caplog.messages)


def test_stop_recording_no_chunks() -> None:
    recorder = AudioRecorder()
    recorder.is_recording = True

    assert recorder.stop_recording() == b""


def test_stop_recording_queue_empty() -> None:
    class StubQueue:
        def __init__(self):
            self.calls = 0

        def empty(self):
            self.calls += 1
            return self.calls > 1

        def get_nowait(self):
            raise queue.Empty

    recorder = AudioRecorder()
    recorder.is_recording = True
    recorder._audio_queue = StubQueue()

    assert recorder.stop_recording() == b""


def test_audio_callback_records_when_enabled() -> None:
    recorder = AudioRecorder()
    recorder.is_recording = True
    data = np.zeros((5, 1), dtype=np.int16)

    recorder._audio_callback(data, 5, {}, 0)

    assert recorder._audio_queue.qsize() == 1


def test_audio_callback_ignores_when_disabled() -> None:
    recorder = AudioRecorder()
    recorder.is_recording = False
    data = np.zeros((5, 1), dtype=np.int16)

    recorder._audio_callback(data, 5, {}, 0)

    assert recorder._audio_queue.qsize() == 0


def test_audio_callback_logs_status() -> None:
    recorder = AudioRecorder()
    recorder.is_recording = False
    data = np.zeros((5, 1), dtype=np.int16)

    recorder._audio_callback(data, 5, {}, 1)


def test_close_stops_stream(mock_sounddevice) -> None:
    recorder = AudioRecorder()
    stream = audio_module.sd.InputStream.return_value
    recorder._stream = stream
    recorder.is_recording = True

    recorder.close()

    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    assert recorder._stream is None


def test_close_no_stream() -> None:
    recorder = AudioRecorder()

    recorder.close()


def test_context_manager_closes_stream(mock_sounddevice) -> None:
    recorder = AudioRecorder()
    stream = audio_module.sd.InputStream.return_value
    recorder._stream = stream

    with recorder:
        pass

    stream.stop.assert_called_once()


def test_list_audio_devices_filters_inputs(mock_sounddevice) -> None:
    devices = audio_module.list_audio_devices()

    assert len(devices) == 1
    assert devices[0]["name"] == "Test Microphone"


def _alias_device(name: str, channels: int) -> dict:
    """Build a device dict for the ALSA-alias filtering tests."""
    return {
        "name": name,
        "max_input_channels": channels,
        "default_samplerate": 48000.0,
        "hostapi": 0,
    }


def test_list_audio_devices_excludes_alsa_plugin_aliases(mock_sounddevice) -> None:
    mock_sounddevice.query_devices.return_value = [
        _alias_device("Test Microphone", 2),
        _alias_device("sysdefault", 128),
        _alias_device("pulse", 32),
        _alias_device("Default Source", 32),
    ]

    devices = audio_module.list_audio_devices()

    assert [d["name"] for d in devices] == ["Test Microphone"]


def test_list_audio_devices_excludes_monitor_devices(mock_sounddevice) -> None:
    mock_sounddevice.query_devices.return_value = [
        {
            "name": "Test Microphone",
            "max_input_channels": 2,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
        {
            "name": "alsa_output.pci-0000_00_1f.3.analog-stereo.monitor",
            "max_input_channels": 2,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
    ]

    devices = audio_module.list_audio_devices()

    assert [d["name"] for d in devices] == ["Test Microphone"]


def test_list_audio_devices_excludes_raw_hw_when_routed_hostapi_available(
    mock_sounddevice,
) -> None:
    mock_sounddevice.query_devices.return_value = [
        {
            "name": "HDA Intel PCH: Analog (hw:0,0)",
            "max_input_channels": 2,
            "default_samplerate": 44100.0,
            "hostapi": 0,
        },
        {
            "name": "alsa_input.pci-0000_00_1f.3.analog-stereo",
            "max_input_channels": 2,
            "default_samplerate": 48000.0,
            "hostapi": 1,
        },
    ]
    mock_sounddevice.query_hostapis.return_value = [
        {"name": "ALSA", "devices": [0]},
        {"name": "PulseAudio", "devices": [1]},
    ]

    devices = audio_module.list_audio_devices()

    assert [d["name"] for d in devices] == ["alsa_input.pci-0000_00_1f.3.analog-stereo"]


def test_list_audio_devices_keeps_raw_hw_when_no_routed_hostapi(mock_sounddevice) -> None:
    mock_sounddevice.query_devices.return_value = [
        {
            "name": "HDA Intel PCH: Analog (hw:0,0)",
            "max_input_channels": 2,
            "default_samplerate": 44100.0,
            "hostapi": 0,
        },
    ]
    mock_sounddevice.query_hostapis.return_value = [{"name": "ALSA", "devices": [0]}]

    devices = audio_module.list_audio_devices()

    assert [d["name"] for d in devices] == ["HDA Intel PCH: Analog (hw:0,0)"]


def test_get_default_input_device_success(mock_sounddevice) -> None:
    mock_sounddevice.query_devices.return_value = {
        "name": "Test Microphone",
        "max_input_channels": 2,
        "default_samplerate": 48000.0,
    }
    device = audio_module.get_default_input_device()

    assert device
    assert device["name"] == "Test Microphone"


def test_get_default_input_device_error(mock_sounddevice) -> None:
    mock_sounddevice.query_devices.side_effect = RuntimeError("boom")

    assert audio_module.get_default_input_device() is None


def test_get_default_input_device_none(mock_sounddevice) -> None:
    mock_sounddevice.default.device = (None, None)

    assert audio_module.get_default_input_device() is None
