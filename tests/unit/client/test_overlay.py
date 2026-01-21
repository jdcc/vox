"""Tests for vox.client.overlay."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from dbus_next.errors import DBusError

from vox.client.overlay import Overlay, OverlayState


@pytest.mark.asyncio
async def test_overlay_start_disabled() -> None:
    overlay = Overlay(enabled=False)
    await overlay.start()
    assert overlay.available is False


@pytest.mark.asyncio
async def test_overlay_connect_success(monkeypatch) -> None:
    bus = MagicMock()
    interface = MagicMock()
    interface.call_set_state = AsyncMock()

    async def connect_stub():
        return bus

    async def introspect_stub(*_args, **_kwargs):
        return MagicMock()

    bus.introspect = AsyncMock(side_effect=introspect_stub)
    bus.get_proxy_object.return_value.get_interface.return_value = interface

    monkeypatch.setattr("vox.client.overlay.MessageBus", lambda: MagicMock(connect=connect_stub))

    overlay = Overlay()
    await overlay.start()

    assert overlay.available is True


@pytest.mark.asyncio
async def test_overlay_connect_existing_interface() -> None:
    overlay = Overlay()
    overlay._interface = MagicMock()

    assert await overlay._connect() is True


@pytest.mark.asyncio
async def test_overlay_connect_failure(monkeypatch) -> None:
    async def connect_stub():
        raise DBusError("org.test", "fail")

    monkeypatch.setattr("vox.client.overlay.MessageBus", lambda: MagicMock(connect=connect_stub))

    overlay = Overlay()
    await overlay.start()

    assert overlay.available is False


@pytest.mark.asyncio
async def test_overlay_set_state_async(monkeypatch) -> None:
    overlay = Overlay()
    interface = MagicMock()
    interface.call_set_state = AsyncMock()
    overlay._interface = interface
    overlay._enabled = True

    await overlay._set_state_async(OverlayState.RECORDING)

    interface.call_set_state.assert_awaited_once_with("recording")


@pytest.mark.asyncio
async def test_overlay_set_state_async_error(monkeypatch) -> None:
    overlay = Overlay()
    interface = MagicMock()
    interface.call_set_state = AsyncMock(side_effect=DBusError("org.test", "fail"))
    overlay._interface = interface
    overlay._enabled = True
    overlay._available = True

    await overlay._set_state_async(OverlayState.RECORDING)

    assert overlay.available is False
    assert overlay._interface is None


def test_overlay_set_state_no_interface() -> None:
    overlay = Overlay()
    overlay.set_state(OverlayState.RECORDING)


def test_overlay_set_state_runs_in_loop(monkeypatch) -> None:
    overlay = Overlay()
    overlay._enabled = True
    overlay._interface = MagicMock()
    overlay._loop = asyncio.get_event_loop()

    called = False

    def run_stub(_coro, _loop):
        _coro.close()
        nonlocal called
        called = True

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", run_stub)

    overlay.set_state(OverlayState.SUCCESS)

    assert called is True


def test_overlay_state_helpers() -> None:
    overlay = Overlay()
    overlay.recording()
    overlay.processing()
    overlay.success()
    overlay.failure()
    overlay.hide()


@pytest.mark.asyncio
async def test_overlay_stop_hides_and_disconnects() -> None:
    overlay = Overlay()
    interface = MagicMock()
    interface.call_set_state = AsyncMock()
    bus = MagicMock()
    overlay._interface = interface
    overlay._bus = bus

    await overlay.stop()

    interface.call_set_state.assert_awaited_once_with("hidden")
    bus.disconnect.assert_called_once()
    assert overlay._interface is None


@pytest.mark.asyncio
async def test_overlay_stop_handles_error() -> None:
    overlay = Overlay()
    interface = MagicMock()
    interface.call_set_state = AsyncMock(side_effect=RuntimeError("boom"))
    overlay._interface = interface

    await overlay.stop()

    assert overlay._interface is None


@pytest.mark.asyncio
async def test_overlay_stop_no_bus() -> None:
    overlay = Overlay()
    overlay._interface = None
    overlay._bus = None

    await overlay.stop()


@pytest.mark.asyncio
async def test_overlay_set_state_async_disabled() -> None:
    overlay = Overlay(enabled=False)
    overlay._interface = MagicMock()

    await overlay._set_state_async(OverlayState.RECORDING)


def test_overlay_set_state_no_loop() -> None:
    overlay = Overlay()
    overlay._enabled = True
    overlay._interface = MagicMock()
    overlay._loop = None

    overlay.set_state(OverlayState.RECORDING)


@pytest.mark.asyncio
async def test_overlay_context_manager(monkeypatch) -> None:
    overlay = Overlay()
    overlay.start = AsyncMock()
    overlay.stop = AsyncMock()

    async with overlay:
        pass

    overlay.start.assert_awaited_once()
    overlay.stop.assert_awaited_once()
