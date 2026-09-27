"""Tests for vox.client.app."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from vox.client.app import Client
from vox.client.connection import ConnectionState, TranscriptionResponse
from vox.config.schema import AudioConfig


def test_on_hotkey_press_starts_recording(monkeypatch) -> None:
    client = Client()
    client.connection._state = ConnectionState.CONNECTED
    client.audio.start_recording = MagicMock()
    client.overlay.recording = MagicMock()

    client._on_hotkey_press()

    assert client._is_recording is True
    client.audio.start_recording.assert_called_once()


def test_on_hotkey_press_flags_failure_when_disconnected() -> None:
    client = Client()
    client.connection._state = ConnectionState.DISCONNECTED
    client.audio.start_recording = MagicMock()
    client.overlay.failure = MagicMock()

    client._on_hotkey_press()

    client.audio.start_recording.assert_not_called()
    client.overlay.failure.assert_called_once()


def test_on_hotkey_press_ignores_when_already_recording() -> None:
    client = Client()
    client.connection._state = ConnectionState.CONNECTED
    client._is_recording = True
    client.audio.start_recording = MagicMock()

    client._on_hotkey_press()

    client.audio.start_recording.assert_not_called()


def test_on_hotkey_press_start_recording_fails(monkeypatch) -> None:
    client = Client()
    client.connection._state = ConnectionState.CONNECTED
    client.audio.start_recording = MagicMock(side_effect=RuntimeError("no device"))
    client.overlay.recording = MagicMock()
    client.overlay.failure = MagicMock()
    client._loop = asyncio.get_event_loop()

    run_stub = MagicMock()
    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", run_stub)

    client._on_hotkey_press()

    assert client._is_recording is False
    client.overlay.recording.assert_not_called()
    client.overlay.failure.assert_called_once()
    run_stub.assert_called_once()
    run_stub.call_args.args[0].close()


def test_on_hotkey_release_sends_audio(monkeypatch) -> None:
    client = Client()
    client._is_recording = True
    client.audio.stop_recording = MagicMock(return_value=b"data")
    client.overlay.processing = MagicMock()
    client._loop = asyncio.get_event_loop()

    called = {}

    def run_stub(coro, _loop):
        coro.close()
        called["coro"] = coro

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", run_stub)

    client._on_hotkey_release()

    assert "coro" in called


def test_on_hotkey_release_empty_audio(monkeypatch) -> None:
    client = Client()
    client._is_recording = True
    client.audio.stop_recording = MagicMock(return_value=b"")
    client.overlay.processing = MagicMock()
    client.overlay.failure = MagicMock()
    client._loop = asyncio.get_event_loop()

    run_stub = MagicMock()
    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", run_stub)

    client._on_hotkey_release()

    client.overlay.failure.assert_called_once()
    run_stub.assert_called_once()
    run_stub.call_args.args[0].close()


def test_on_hotkey_release_empty_audio_no_loop() -> None:
    client = Client()
    client._is_recording = True
    client.audio.stop_recording = MagicMock(return_value=b"")
    client.overlay.processing = MagicMock()
    client.overlay.failure = MagicMock()
    client._loop = None

    client._on_hotkey_release()

    client.overlay.failure.assert_called_once()


def test_on_hotkey_release_not_recording() -> None:
    client = Client()
    client._is_recording = False
    client.audio.stop_recording = MagicMock()

    client._on_hotkey_release()

    client.audio.stop_recording.assert_not_called()


def test_on_transcription_processing() -> None:
    client = Client()
    response = TranscriptionResponse(text="partial", processing=True)

    client._on_transcription(response)

    assert client._pending_output is None


def test_on_transcription_final(monkeypatch) -> None:
    client = Client()
    response = TranscriptionResponse(text="final", processing=False)
    client.overlay.success = MagicMock()
    client._loop = asyncio.get_event_loop()

    called = {}

    def run_stub(coro, _loop):
        coro.close()
        called["coro"] = coro

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", run_stub)

    client._on_transcription(response)

    assert client._pending_output == "final"
    assert "coro" in called


def test_on_transcription_final_no_loop() -> None:
    client = Client()
    response = TranscriptionResponse(text="final", processing=False)
    client.overlay.success = MagicMock()

    client._on_transcription(response)

    assert client._pending_output == "final"


def test_on_connection_state_change() -> None:
    client = Client()
    client._on_connection_state_change(ConnectionState.CONNECTED)
    client._on_connection_state_change(ConnectionState.DISCONNECTED)
    client._on_connection_state_change(ConnectionState.CONNECTING)


def test_disconnect_while_awaiting_result_flags_failure() -> None:
    client = Client()
    client._awaiting_result = True
    client.overlay.failure = MagicMock()

    client._on_connection_state_change(ConnectionState.DISCONNECTED)

    client.overlay.failure.assert_called_once()
    assert client._awaiting_result is False


def test_disconnect_while_idle_does_not_flag_failure() -> None:
    client = Client()
    client.overlay.failure = MagicMock()

    client._on_connection_state_change(ConnectionState.DISCONNECTED)

    client.overlay.failure.assert_not_called()


def test_on_server_error_flags_failure() -> None:
    client = Client()
    client._awaiting_result = True
    client.overlay.failure = MagicMock()

    client._on_server_error("Missing API key")

    client.overlay.failure.assert_called_once()
    assert client._awaiting_result is False


def test_on_hotkey_release_marks_awaiting_result(monkeypatch) -> None:
    client = Client()
    client._is_recording = True
    client.audio.stop_recording = MagicMock(return_value=b"data")
    client.overlay.processing = MagicMock()
    client._loop = asyncio.get_event_loop()
    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", lambda coro, _loop: coro.close())

    client._on_hotkey_release()

    assert client._awaiting_result is True


def test_on_transcription_final_clears_awaiting_result() -> None:
    client = Client()
    client._awaiting_result = True
    client.overlay.success = MagicMock()

    client._on_transcription(TranscriptionResponse(text="final", processing=False))

    assert client._awaiting_result is False


@pytest.mark.asyncio
async def test_send_audio_success() -> None:
    client = Client()
    client.connection.send_audio = AsyncMock(return_value=True)
    client.overlay.failure = MagicMock()

    await client._send_audio(b"data")

    client.connection.send_audio.assert_awaited_once_with(
        b"data", sample_rate=client.audio.sample_rate, channels=client.audio.channels
    )
    client.overlay.failure.assert_not_called()


@pytest.mark.asyncio
async def test_send_audio_failure_flags_failure() -> None:
    client = Client()
    client.connection.send_audio = AsyncMock(return_value=False)
    client.overlay.failure = MagicMock()

    await client._send_audio(b"data")

    client.overlay.failure.assert_called_once()


def test_client_uses_configured_microphone(monkeypatch, sample_config) -> None:
    sample_config.audio = AudioConfig(input_device="Desk Mic")
    monkeypatch.setattr(
        "vox.client.app.list_audio_devices",
        lambda: [
            {"index": 0, "name": "USB Mic", "channels": 1, "sample_rate": 48000},
            {"index": 3, "name": "Desk Mic", "channels": 2, "sample_rate": 44100},
        ],
    )
    preferred_loader = MagicMock(return_value="USB Mic")
    monkeypatch.setattr("vox.client.app.load_preferred_device_name", preferred_loader)

    client = Client(config=sample_config)

    assert client.audio.device == 3
    preferred_loader.assert_not_called()


def test_client_uses_remembered_microphone_when_config_unset(monkeypatch, sample_config) -> None:
    sample_config.audio = AudioConfig(input_device=None)
    monkeypatch.setattr(
        "vox.client.app.list_audio_devices",
        lambda: [
            {"index": 4, "name": "USB Mic", "channels": 1, "sample_rate": 48000},
        ],
    )
    monkeypatch.setattr(
        "vox.client.app.load_preferred_device_name", lambda _devices: "USB Mic"
    )

    client = Client(config=sample_config)

    assert client.audio.device == 4


def test_client_uses_default_when_configured_microphone_missing(monkeypatch, sample_config) -> None:
    sample_config.audio = AudioConfig(input_device="Missing Mic")
    monkeypatch.setattr(
        "vox.client.app.list_audio_devices",
        lambda: [
            {"index": 0, "name": "USB Mic", "channels": 1, "sample_rate": 48000},
        ],
    )
    preferred_loader = MagicMock(return_value="USB Mic")
    monkeypatch.setattr("vox.client.app.load_preferred_device_name", preferred_loader)

    client = Client(config=sample_config)

    assert client.audio.device is None
    preferred_loader.assert_not_called()


def test_client_uses_default_when_no_remembered_selection(monkeypatch, sample_config) -> None:
    sample_config.audio = AudioConfig(input_device=None)
    monkeypatch.setattr(
        "vox.client.app.list_audio_devices",
        lambda: [
            {"index": 0, "name": "USB Mic", "channels": 1, "sample_rate": 48000},
        ],
    )
    monkeypatch.setattr("vox.client.app.load_preferred_device_name", lambda _devices: None)

    client = Client(config=sample_config)

    assert client.audio.device is None


def test_client_uses_default_when_remembered_microphone_missing(monkeypatch, sample_config) -> None:
    sample_config.audio = AudioConfig(input_device=None)
    monkeypatch.setattr(
        "vox.client.app.list_audio_devices",
        lambda: [
            {"index": 0, "name": "USB Mic", "channels": 1, "sample_rate": 48000},
        ],
    )
    monkeypatch.setattr(
        "vox.client.app.load_preferred_device_name", lambda _devices: "Missing Mic"
    )

    client = Client(config=sample_config)

    assert client.audio.device is None


def test_on_hotkey_press_refreshes_device_before_recording(monkeypatch) -> None:
    client = Client()
    client.connection._state = ConnectionState.CONNECTED
    client.audio.start_recording = MagicMock()
    client.audio.set_device = MagicMock()
    client.overlay.recording = MagicMock()
    monkeypatch.setattr(client, "_get_selected_device", lambda: 3)

    client._on_hotkey_press()

    client.audio.set_device.assert_called_once_with(3)


@pytest.mark.asyncio
async def test_output_text(monkeypatch) -> None:
    client = Client()
    client.output.output = AsyncMock()
    client.overlay.hide = MagicMock()
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await client._output_text("hi")

    client.output.output.assert_awaited_once_with("hi")
    client.overlay.hide.assert_called_once()


@pytest.mark.asyncio
async def test_output_text_empty(monkeypatch) -> None:
    client = Client()
    client.output.output = AsyncMock()
    client.overlay.hide = MagicMock()
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await client._output_text("")

    client.output.output.assert_not_called()
    client.overlay.hide.assert_called_once()


@pytest.mark.asyncio
async def test_start_success(monkeypatch) -> None:
    client = Client()

    monkeypatch.setattr("vox.client.app.check_extension_available", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "vox.client.app.check_wayland_tools",
        lambda: {"wl-copy": True, "wl-paste": True},
    )
    client.output.start = AsyncMock()
    client.overlay.start = AsyncMock()
    client.connection.start = AsyncMock()

    hotkey = MagicMock()
    hotkey.start = AsyncMock()
    monkeypatch.setattr("vox.client.app.HotkeyListener", lambda **_kwargs: hotkey)

    async def sleep_stub(_delay):
        client._running = False

    monkeypatch.setattr(asyncio, "sleep", sleep_stub)

    await client.start()

    client.connection.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_hotkey_failure(monkeypatch) -> None:
    client = Client()

    monkeypatch.setattr("vox.client.app.check_extension_available", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "vox.client.app.check_wayland_tools",
        lambda: {"wl-copy": False, "wl-paste": True},
    )
    client.output.start = AsyncMock()
    client.overlay.start = AsyncMock()
    client.connection.start = AsyncMock()

    hotkey = MagicMock()
    hotkey.start = AsyncMock(side_effect=RuntimeError("fail"))
    monkeypatch.setattr("vox.client.app.HotkeyListener", lambda **_kwargs: hotkey)

    with pytest.raises(RuntimeError, match="fail"):
        await client.start()


@pytest.mark.asyncio
async def test_start_waits_for_late_extension(monkeypatch) -> None:
    client = Client()

    monkeypatch.setattr("vox.client.app.check_extension_available", AsyncMock(return_value=False))
    wait = AsyncMock(return_value=True)
    monkeypatch.setattr("vox.client.app.wait_for_extension", wait)
    monkeypatch.setattr(
        "vox.client.app.check_wayland_tools",
        lambda: {"wl-copy": True, "wl-paste": True},
    )
    client.output.start = AsyncMock()
    client.overlay.start = AsyncMock()
    client.connection.start = AsyncMock()

    hotkey = MagicMock()
    hotkey.start = AsyncMock()
    monkeypatch.setattr("vox.client.app.HotkeyListener", lambda **_kwargs: hotkey)

    async def sleep_stub(_delay):
        client._running = False

    monkeypatch.setattr(asyncio, "sleep", sleep_stub)

    await client.start()

    wait.assert_awaited_once()
    client.overlay.start.assert_awaited_once()
    hotkey.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_fails_when_extension_never_appears(monkeypatch) -> None:
    client = Client()

    monkeypatch.setattr("vox.client.app.check_extension_available", AsyncMock(return_value=False))
    monkeypatch.setattr("vox.client.app.wait_for_extension", AsyncMock(return_value=False))
    client.overlay.start = AsyncMock()
    client.connection.start = AsyncMock()

    with pytest.raises(RuntimeError, match="extension not available"):
        await client.start()

    client.overlay.start.assert_not_called()
    client.connection.start.assert_not_called()


@pytest.mark.asyncio
async def test_stop(monkeypatch) -> None:
    client = Client()
    client.hotkey = MagicMock()
    client.hotkey.stop = AsyncMock()
    client.connection.disconnect = AsyncMock()
    client.audio.close = MagicMock()
    client.overlay.stop = AsyncMock()

    await client.stop()

    client.hotkey.stop.assert_awaited_once()
    client.connection.disconnect.assert_awaited_once()
    client.audio.close.assert_called_once()
    client.overlay.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_does_not_block_on_portal_setup(monkeypatch) -> None:
    client = Client()

    monkeypatch.setattr("vox.client.app.check_extension_available", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "vox.client.app.check_wayland_tools",
        lambda: {"wl-copy": True, "wl-paste": True},
    )
    portal_pending = asyncio.Event()

    async def blocked_output_start():
        await portal_pending.wait()

    client.output.start = blocked_output_start
    client.output.stop = AsyncMock()
    client.overlay.start = AsyncMock()
    client.overlay.stop = AsyncMock()
    client.connection.start = AsyncMock()
    client.connection.disconnect = AsyncMock()

    hotkey = MagicMock()
    hotkey.start = AsyncMock()
    hotkey.stop = AsyncMock()
    monkeypatch.setattr("vox.client.app.HotkeyListener", lambda **_kwargs: hotkey)

    real_sleep = asyncio.sleep

    async def sleep_stub(_delay):
        client._running = False
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", sleep_stub)

    await client.start()

    hotkey.start.assert_awaited_once()
    task = client._output_start_task
    assert task is not None and not task.done()

    await client.stop()

    assert task.cancelled()
    client.output.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_no_hotkey(monkeypatch) -> None:
    client = Client()
    client.hotkey = None
    client.connection.disconnect = AsyncMock()
    client.audio.close = MagicMock()
    client.overlay.stop = AsyncMock()

    await client.stop()

    client.connection.disconnect.assert_awaited_once()
    client.audio.close.assert_called_once()
    client.overlay.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_client(monkeypatch) -> None:
    from vox.client import app as app_module

    runner = AsyncMock()
    stopper = AsyncMock()
    monkeypatch.setattr(app_module.Client, "start", runner)
    monkeypatch.setattr(app_module.Client, "stop", stopper)

    handled = {}

    class FakeLoop:
        def add_signal_handler(self, _sig, handler):
            handled["handler"] = handler

    monkeypatch.setattr(asyncio, "get_event_loop", lambda: FakeLoop())

    def create_task_stub(coro):
        coro.close()
        return None

    monkeypatch.setattr(asyncio, "create_task", create_task_stub)

    await app_module.run_client()

    runner.assert_awaited_once()
    assert "handler" in handled
    handled["handler"]()
