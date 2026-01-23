"""Tests for portal input handling."""

from __future__ import annotations

import pytest
from dbus_next import Message, MessageType, Variant

from vox.client import portal_input as portal_module

from vox.client.portal_input import (
    KEY_LEFTCTRL,
    KEY_LEFTSHIFT,
    KEY_V,
    DESKTOP_PATH,
    REMOTE_DESKTOP_IFACE,
    KeyPress,
    PortalInput,
    PortalInputError,
    char_to_keypress,
)


class _FakeBus:
    def __init__(self, responses: dict[str, tuple[int, dict[str, Variant]]], close_fails: bool):
        self._responses = responses
        self._close_fails = close_fails
        self._handlers = []
        self._emitted = set()
        self.calls: list[tuple] = []
        self.disconnected = False

    async def connect(self):
        return self

    async def call(self, message: Message) -> Message:
        self.calls.append((message.member, message.body))
        if message.member in {"CreateSession", "SelectDevices", "Start"}:
            if message.member == "CreateSession":
                request_path = "/request/1"
            elif message.member == "SelectDevices":
                request_path = "/request/2"
            else:
                request_path = "/request/3"
            return Message(
                message_type=MessageType.METHOD_RETURN,
                reply_serial=1,
                body=[request_path],
            )
        if message.member == "NotifyKeyboardKeycode":
            return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1, body=[])
        if message.member == "Close":
            if self._close_fails:
                return Message(
                    message_type=MessageType.ERROR,
                    error_name="CloseFailed",
                    reply_serial=1,
                )
            return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1, body=[])
        return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1, body=[])

    def add_message_handler(self, handler):
        self._handlers.append(handler)
        for path, (response, results) in self._responses.items():
            if path in self._emitted:
                continue
            msg = Message(
                message_type=MessageType.SIGNAL,
                path=path,
                interface="org.freedesktop.portal.Request",
                member="Response",
                body=[response, results],
            )
            handled = handler(msg)
            if handled:
                self._emitted.add(path)
                break

    def remove_message_handler(self, handler):
        if handler in self._handlers:
            self._handlers.remove(handler)

    def disconnect(self):
        self.disconnected = True


def _portal_with_fake_bus(
    responses: dict[str, tuple[int, dict[str, Variant]]],
    session_should_fail: bool = False,
) -> PortalInput:
    bus = _FakeBus(responses, close_fails=session_should_fail)

    def bus_factory():
        return bus

    portal = PortalInput(bus_factory=bus_factory)
    portal._fake_bus = bus
    return portal


def test_char_to_keypress_basic() -> None:
    assert char_to_keypress("a") == KeyPress(30, needs_shift=False)
    assert char_to_keypress("A") == KeyPress(30, needs_shift=True)
    assert char_to_keypress("1") == KeyPress(2, needs_shift=False)
    assert char_to_keypress("#") == KeyPress(4, needs_shift=True)
    assert char_to_keypress("{") == KeyPress(26, needs_shift=True)
    assert char_to_keypress("?") == KeyPress(53, needs_shift=True)
    assert char_to_keypress("\n") == KeyPress(28, needs_shift=False)
    assert char_to_keypress("€") is None


def test_char_to_keypress_invalid_length() -> None:
    assert char_to_keypress("") is None
    assert char_to_keypress("ab") is None


def test_char_to_keypress_missing_mapping(monkeypatch) -> None:
    monkeypatch.delitem(portal_module._LETTER_KEYCODES, "a", raising=False)
    assert char_to_keypress("a") is None
    monkeypatch.delitem(portal_module._DIGIT_KEYCODES, "1", raising=False)
    assert char_to_keypress("1") is None


@pytest.mark.asyncio
async def test_portal_input_start_stop_success() -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)

    await portal.start()

    assert portal.active is True
    assert portal._session_handle == "/session/1"
    assert portal._fake_bus.calls[0][0] == "CreateSession"

    await portal.stop()

    assert portal.active is False
    assert portal._fake_bus.disconnected is True


@pytest.mark.asyncio
async def test_portal_input_start_already_active() -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)
    portal._active = True

    await portal.start()

    assert portal._fake_bus.calls == []


@pytest.mark.asyncio
async def test_portal_input_start_rejected() -> None:
    responses = {
        "/request/1": (1, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)

    with pytest.raises(PortalInputError):
        await portal.start()

    assert portal.active is False


@pytest.mark.asyncio
async def test_portal_input_select_devices_rejected() -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (1, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)

    with pytest.raises(PortalInputError):
        await portal.start()


@pytest.mark.asyncio
async def test_portal_input_start_rejected_on_start() -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (1, {}),
    }
    portal = _portal_with_fake_bus(responses)

    with pytest.raises(PortalInputError):
        await portal.start()


@pytest.mark.asyncio
async def test_portal_input_session_handle_missing() -> None:
    responses = {
        "/request/1": (0, {}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)

    with pytest.raises(PortalInputError):
        await portal.start()


@pytest.mark.asyncio
async def test_portal_input_send_keycode_and_type(monkeypatch) -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)
    await portal.start()

    await portal.send_keycode(KEY_LEFTCTRL, True)
    await portal.send_keycode(KEY_LEFTCTRL, False)
    await portal.send_paste()

    # Only check that notify calls happened with expected keycodes.
    notify_calls = [call for call in portal._fake_bus.calls if call[0] == "NotifyKeyboardKeycode"]
    keycodes = [call[1][2] for call in notify_calls]
    assert KEY_LEFTCTRL in keycodes
    assert KEY_V in keycodes

    await portal.type_text("A")
    notify_calls = [call for call in portal._fake_bus.calls if call[0] == "NotifyKeyboardKeycode"]
    assert KEY_LEFTSHIFT in [call[1][2] for call in notify_calls]


@pytest.mark.asyncio
async def test_portal_input_send_keycode_without_session() -> None:
    portal = PortalInput(bus_factory=lambda: _FakeBus({}, False))
    with pytest.raises(PortalInputError):
        await portal.send_keycode(10, True)


@pytest.mark.asyncio
async def test_portal_input_stop_handles_close_error() -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses, session_should_fail=True)
    await portal.start()

    await portal.stop()

    assert portal.active is False


@pytest.mark.asyncio
async def test_portal_input_type_text_unsupported_char(caplog) -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)
    await portal.start()

    await portal.type_text("\x07")

    assert "Unsupported character" in caplog.text


@pytest.mark.asyncio
async def test_portal_input_type_text_no_shift() -> None:
    responses = {
        "/request/1": (0, {"session_handle": Variant("o", "/session/1")}),
        "/request/2": (0, {}),
        "/request/3": (0, {}),
    }
    portal = _portal_with_fake_bus(responses)
    await portal.start()

    await portal.type_text("a")

    notify_calls = [call for call in portal._fake_bus.calls if call[0] == "NotifyKeyboardKeycode"]
    assert KEY_LEFTSHIFT not in [call[1][2] for call in notify_calls]


@pytest.mark.asyncio
async def test_portal_input_stop_without_bus() -> None:
    portal = PortalInput(bus_factory=lambda: _FakeBus({}, False))
    await portal.stop()
    assert portal.active is False


@pytest.mark.asyncio
async def test_portal_input_request_multiple_responses() -> None:
    responses = {"/request/multi": (0, {})}
    portal = _portal_with_fake_bus(responses)
    portal._bus = await portal._bus_factory().connect()

    response, results = await portal._request("/request/multi")

    assert response == 0
    assert results == {}


@pytest.mark.asyncio
async def test_portal_input_request_filters_messages() -> None:
    class _HandlerBus:
        def __init__(self, messages):
            self._messages = messages
            self._handlers = []

        def add_message_handler(self, handler):
            self._handlers.append(handler)
            for message in self._messages:
                handler(message)

        def remove_message_handler(self, handler):
            if handler in self._handlers:
                self._handlers.remove(handler)

    messages = [
        Message(
            message_type=MessageType.METHOD_RETURN,
            reply_serial=1,
            path="/request/ok",
            interface="org.freedesktop.portal.Request",
            member="Response",
            body=[0, {}],
        ),
        Message(
            message_type=MessageType.SIGNAL,
            path="/request/other",
            interface="org.freedesktop.portal.Request",
            member="Response",
            body=[0, {}],
        ),
        Message(
            message_type=MessageType.SIGNAL,
            path="/request/ok",
            interface="org.freedesktop.portal.Other",
            member="Response",
            body=[0, {}],
        ),
        Message(
            message_type=MessageType.SIGNAL,
            path="/request/ok",
            interface="org.freedesktop.portal.Request",
            member="Other",
            body=[0, {}],
        ),
        Message(
            message_type=MessageType.SIGNAL,
            path="/request/ok",
            interface="org.freedesktop.portal.Request",
            member="Response",
            body=[0, {"session_handle": Variant("o", "/session/ok")}],
        ),
        Message(
            message_type=MessageType.SIGNAL,
            path="/request/ok",
            interface="org.freedesktop.portal.Request",
            member="Response",
            body=[0, {"session_handle": Variant("o", "/session/ok")}],
        ),
    ]
    portal = PortalInput()
    portal._bus = _HandlerBus(messages)

    response, results = await portal._request("/request/ok")

    assert response == 0
    assert results["session_handle"].value == "/session/ok"


@pytest.mark.asyncio
async def test_portal_input_call_without_bus() -> None:
    portal = PortalInput()

    with pytest.raises(PortalInputError):
        await portal._call(
            path=DESKTOP_PATH,
            interface=REMOTE_DESKTOP_IFACE,
            member="NotifyKeyboardKeycode",
            signature="",
            body=[],
        )


@pytest.mark.asyncio
async def test_portal_input_call_error_response() -> None:
    class _ErrorBus:
        async def call(self, _message: Message) -> Message:
            return Message(
                message_type=MessageType.ERROR,
                error_name="org.vox.Error",
                reply_serial=1,
            )

    portal = PortalInput()
    portal._bus = _ErrorBus()

    with pytest.raises(PortalInputError, match="org.vox.Error"):
        await portal._call(
            path=DESKTOP_PATH,
            interface=REMOTE_DESKTOP_IFACE,
            member="NotifyKeyboardKeycode",
            signature="",
            body=[],
        )
