"""Tests for vox.client.hotkey."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dbus_next.errors import DBusError

from vox.client.hotkey import HotkeyListener, check_extension_available, wait_for_extension


@pytest.mark.asyncio
async def test_hotkey_start_success(monkeypatch) -> None:
    bus = MagicMock()
    interface = MagicMock()
    interface.on_hotkey_pressed = MagicMock()
    interface.on_hotkey_released = MagicMock()
    proxy = MagicMock()
    proxy.get_interface.return_value = interface
    bus.introspect = AsyncMock(return_value=MagicMock())
    bus.get_proxy_object.return_value = proxy

    async def connect_stub():
        return bus

    monkeypatch.setattr("vox.client.hotkey.MessageBus", lambda: MagicMock(connect=connect_stub))

    pressed = []
    released = []

    listener = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: pressed.append(True),
        on_release=lambda: released.append(True),
    )

    await listener.start()
    listener._on_hotkey_pressed_signal()
    listener._on_hotkey_released_signal()

    assert pressed
    assert released


def test_hotkey_signal_error_handlers() -> None:
    errors = {"press": False, "release": False}

    def on_press():
        errors["press"] = True
        raise RuntimeError("boom")

    def on_release():
        errors["release"] = True
        raise RuntimeError("boom")

    listener = HotkeyListener(
        hotkey="ctrl+space",
        on_press=on_press,
        on_release=on_release,
    )

    listener._on_hotkey_pressed_signal()
    listener._on_hotkey_released_signal()

    assert errors["press"] is True
    assert errors["release"] is True


@pytest.mark.asyncio
async def test_hotkey_start_failure(monkeypatch) -> None:
    async def connect_stub():
        raise DBusError("org.test", "fail")

    monkeypatch.setattr("vox.client.hotkey.MessageBus", lambda: MagicMock(connect=connect_stub))

    listener = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: None,
        on_release=lambda: None,
    )

    with pytest.raises(RuntimeError):
        await listener.start()


@pytest.mark.asyncio
async def test_hotkey_stop_disconnects() -> None:
    listener = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: None,
        on_release=lambda: None,
    )

    bus = MagicMock()
    listener._bus = bus

    await listener.stop()

    bus.disconnect.assert_called_once()
    assert listener._interface is None


@pytest.mark.asyncio
async def test_hotkey_stop_no_bus() -> None:
    listener = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: None,
        on_release=lambda: None,
    )

    await listener.stop()


@pytest.mark.asyncio
async def test_check_extension_available_success(monkeypatch) -> None:
    bus = MagicMock()
    interface = MagicMock()
    interface.call_get_state = AsyncMock()
    proxy = MagicMock()
    proxy.get_interface.return_value = interface
    bus.introspect = AsyncMock(return_value=MagicMock())
    bus.get_proxy_object.return_value = proxy

    async def connect_stub():
        return bus

    monkeypatch.setattr("vox.client.hotkey.MessageBus", lambda: MagicMock(connect=connect_stub))

    assert await check_extension_available() is True


@pytest.mark.asyncio
async def test_check_extension_available_dbus_error(monkeypatch) -> None:
    async def connect_stub():
        raise DBusError("org.test", "fail")

    monkeypatch.setattr("vox.client.hotkey.MessageBus", lambda: MagicMock(connect=connect_stub))

    assert await check_extension_available() is False


@pytest.mark.asyncio
async def test_check_extension_available_exception(monkeypatch) -> None:
    async def connect_stub():
        raise RuntimeError("boom")

    monkeypatch.setattr("vox.client.hotkey.MessageBus", lambda: MagicMock(connect=connect_stub))

    assert await check_extension_available() is False


@pytest.mark.asyncio
async def test_check_extension_available_disconnects_on_failure(monkeypatch) -> None:
    bus = MagicMock()
    bus.introspect = AsyncMock(side_effect=DBusError("org.test", "no such name"))

    async def connect_stub():
        return bus

    monkeypatch.setattr("vox.client.hotkey.MessageBus", lambda: MagicMock(connect=connect_stub))

    assert await check_extension_available() is False
    bus.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_extension_retries_until_available(monkeypatch) -> None:
    check = AsyncMock(side_effect=[False, False, True])
    sleep = AsyncMock()
    monkeypatch.setattr("vox.client.hotkey.check_extension_available", check)
    monkeypatch.setattr("vox.client.hotkey.asyncio.sleep", sleep)

    assert await wait_for_extension(attempts=5, interval=0.5) is True
    assert check.await_count == 3
    sleep.assert_awaited_with(0.5)


@pytest.mark.asyncio
async def test_wait_for_extension_gives_up(monkeypatch) -> None:
    check = AsyncMock(return_value=False)
    monkeypatch.setattr("vox.client.hotkey.check_extension_available", check)
    monkeypatch.setattr("vox.client.hotkey.asyncio.sleep", AsyncMock())

    assert await wait_for_extension(attempts=3) is False
    assert check.await_count == 3


def test_check_input_permissions_true(monkeypatch) -> None:
    from vox.client.hotkey import check_input_permissions

    monkeypatch.setattr("grp.getgrnam", lambda _name: MagicMock(gr_gid=100))
    monkeypatch.setattr("os.getgroups", lambda: [100, 200])

    assert check_input_permissions() is True


def test_check_input_permissions_missing_group(monkeypatch) -> None:
    def getgrnam_stub(_name):
        raise KeyError("missing")

    monkeypatch.setattr("grp.getgrnam", getgrnam_stub)

    from vox.client.hotkey import check_input_permissions

    assert check_input_permissions() is False


def test_check_input_permissions_not_in_group(monkeypatch) -> None:
    from vox.client.hotkey import check_input_permissions

    monkeypatch.setattr("grp.getgrnam", lambda _name: MagicMock(gr_gid=100))
    monkeypatch.setattr("os.getgroups", lambda: [200, 300])

    assert check_input_permissions() is False
