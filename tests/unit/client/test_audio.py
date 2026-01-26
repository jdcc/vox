"""Tests for vox.client.audio."""

import queue
from unittest.mock import MagicMock

import numpy as np

from vox.client import audio as audio_module
from vox.client.audio import AudioRecorder


def test_start_recording_initializes_stream(mock_sounddevice) -> None:
    recorder = AudioRecorder()

    recorder.start_recording()

    assert recorder.is_recording is True
    mock_sounddevice.InputStream.assert_called_once()
    mock_sounddevice.InputStream.return_value.start.assert_called_once()


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


def test_calculate_level_clamps_to_one() -> None:
    recorder = AudioRecorder()
    data = np.full((10, 1), 32767, dtype=np.int16)

    level = recorder._calculate_level(data)

    assert level == 1.0


def test_audio_callback_reports_level(monkeypatch) -> None:
    levels = []

    def on_level(level: float) -> None:
        levels.append(level)

    recorder = AudioRecorder(on_level=on_level)
    recorder.is_recording = True
    recorder._last_level_time = 0.0
    recorder._level_interval = 0.1
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: 1.0)

    data = np.zeros((5, 1), dtype=np.int16)
    recorder._audio_callback(data, 5, {}, 0)

    assert len(levels) == 1


def test_audio_callback_level_handler_error(monkeypatch) -> None:
    def on_level(_level: float) -> None:
        raise RuntimeError("boom")

    recorder = AudioRecorder(on_level=on_level)
    recorder.is_recording = True
    recorder._last_level_time = 0.0
    recorder._level_interval = 0.1
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: 1.0)

    data = np.zeros((5, 1), dtype=np.int16)
    recorder._audio_callback(data, 5, {}, 0)


def test_audio_callback_skips_level_when_throttled(monkeypatch) -> None:
    levels = []

    def on_level(level: float) -> None:
        levels.append(level)

    recorder = AudioRecorder(on_level=on_level)
    recorder.is_recording = True
    recorder._last_level_time = 0.95
    recorder._level_interval = 0.1
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: 1.0)

    data = np.zeros((5, 1), dtype=np.int16)
    recorder._audio_callback(data, 5, {}, 0)

    assert levels == []


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
