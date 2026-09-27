"""Portal-based input injection via xdg-desktop-portal."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Callable

from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

logger = logging.getLogger(__name__)

DESKTOP_SERVICE = "org.freedesktop.portal.Desktop"
DESKTOP_PATH = "/org/freedesktop/portal/desktop"
REMOTE_DESKTOP_IFACE = "org.freedesktop.portal.RemoteDesktop"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"

DEVICE_KEYBOARD = 1

# Upper bound on waiting for a portal Response, including time for the user
# to answer a permission dialog. Without it a lost request hangs forever.
REQUEST_TIMEOUT = 120.0

KEY_LEFTSHIFT = 42
KEY_LEFTCTRL = 29
KEY_V = 47


class PortalInputError(RuntimeError):
    """Portal input error."""


@dataclass(frozen=True)
class KeyPress:
    keycode: int
    needs_shift: bool = False


_LETTER_KEYCODES = {
    "a": 30,
    "b": 48,
    "c": 46,
    "d": 32,
    "e": 18,
    "f": 33,
    "g": 34,
    "h": 35,
    "i": 23,
    "j": 36,
    "k": 37,
    "l": 38,
    "m": 50,
    "n": 49,
    "o": 24,
    "p": 25,
    "q": 16,
    "r": 19,
    "s": 31,
    "t": 20,
    "u": 22,
    "v": 47,
    "w": 17,
    "x": 45,
    "y": 21,
    "z": 44,
}

_DIGIT_KEYCODES = {
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
}

_SYMBOL_KEYCODES: dict[str, KeyPress] = {
    " ": KeyPress(57),
    "\t": KeyPress(15),
    "\n": KeyPress(28),
    "-": KeyPress(12),
    "_": KeyPress(12, needs_shift=True),
    "=": KeyPress(13),
    "+": KeyPress(13, needs_shift=True),
    "[": KeyPress(26),
    "{": KeyPress(26, needs_shift=True),
    "]": KeyPress(27),
    "}": KeyPress(27, needs_shift=True),
    "\\": KeyPress(43),
    "|": KeyPress(43, needs_shift=True),
    ";": KeyPress(39),
    ":": KeyPress(39, needs_shift=True),
    "'": KeyPress(40),
    "\"": KeyPress(40, needs_shift=True),
    "`": KeyPress(41),
    "~": KeyPress(41, needs_shift=True),
    ",": KeyPress(51),
    "<": KeyPress(51, needs_shift=True),
    ".": KeyPress(52),
    ">": KeyPress(52, needs_shift=True),
    "/": KeyPress(53),
    "?": KeyPress(53, needs_shift=True),
    "!": KeyPress(_DIGIT_KEYCODES["1"], needs_shift=True),
    "@": KeyPress(_DIGIT_KEYCODES["2"], needs_shift=True),
    "#": KeyPress(_DIGIT_KEYCODES["3"], needs_shift=True),
    "$": KeyPress(_DIGIT_KEYCODES["4"], needs_shift=True),
    "%": KeyPress(_DIGIT_KEYCODES["5"], needs_shift=True),
    "^": KeyPress(_DIGIT_KEYCODES["6"], needs_shift=True),
    "&": KeyPress(_DIGIT_KEYCODES["7"], needs_shift=True),
    "*": KeyPress(_DIGIT_KEYCODES["8"], needs_shift=True),
    "(": KeyPress(_DIGIT_KEYCODES["9"], needs_shift=True),
    ")": KeyPress(_DIGIT_KEYCODES["0"], needs_shift=True),
}


def char_to_keypress(ch: str) -> KeyPress | None:
    """Convert a character to a keycode/shift combo for a US layout."""
    if len(ch) != 1:
        return None

    if ch in _SYMBOL_KEYCODES:
        return _SYMBOL_KEYCODES[ch]

    if ch.isalpha():
        keycode = _LETTER_KEYCODES.get(ch.lower())
        if keycode is None:
            return None
        return KeyPress(keycode, needs_shift=ch.isupper())

    if ch.isdigit():
        keycode = _DIGIT_KEYCODES.get(ch)
        if keycode is None:
            return None
        return KeyPress(keycode)

    return None


class PortalInput:
    """Long-lived portal session for keyboard injection."""

    def __init__(self, bus_factory: Callable[[], MessageBus] = MessageBus) -> None:
        self._bus_factory = bus_factory
        self._bus: MessageBus | None = None
        self._desktop_iface = None
        self._session_handle: str | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    async def start(self) -> None:
        """Start a portal session and keep it alive."""
        if self._active:
            return
        try:
            self._bus = await self._bus_factory().connect()
            self._session_handle = await self._create_session()
            await self._select_devices(DEVICE_KEYBOARD)
            await self._start_session(DEVICE_KEYBOARD)
            self._active = True
        except (DBusError, PortalInputError, asyncio.TimeoutError) as exc:
            await self.stop()
            raise PortalInputError(str(exc)) from exc

    async def stop(self) -> None:
        """Stop the portal session."""
        if self._bus and self._session_handle:
            try:
                await self._call(
                    path=self._session_handle,
                    interface=SESSION_IFACE,
                    member="Close",
                    signature="",
                    body=[],
                )
            except Exception as exc:
                logger.debug("Failed closing portal session: %s", exc)
        if self._bus:
            self._bus.disconnect()
        self._bus = None
        self._desktop_iface = None
        self._session_handle = None
        self._active = False

    async def send_keycode(self, keycode: int, pressed: bool) -> None:
        """Send a key press/release."""
        if not self._bus or not self._session_handle:
            raise PortalInputError("Portal session not started")
        state = 1 if pressed else 0
        await self._call(
            path=DESKTOP_PATH,
            interface=REMOTE_DESKTOP_IFACE,
            member="NotifyKeyboardKeycode",
            signature="oa{sv}iu",
            body=[self._session_handle, {}, int(keycode), int(state)],
        )

    async def send_key_press(self, keycode: int) -> None:
        """Send a key press and release."""
        await self.send_keycode(keycode, True)
        await self.send_keycode(keycode, False)

    async def send_paste(self) -> None:
        """Send Ctrl+V."""
        await self.send_keycode(KEY_LEFTCTRL, True)
        await self.send_keycode(KEY_V, True)
        await self.send_keycode(KEY_V, False)
        await self.send_keycode(KEY_LEFTCTRL, False)

    async def type_text(self, text: str) -> None:
        """Type text using keycodes for a US layout."""
        for ch in text:
            keypress = char_to_keypress(ch)
            if keypress is None:
                logger.warning("Unsupported character for portal typing: %r", ch)
                continue
            if keypress.needs_shift:
                await self.send_keycode(KEY_LEFTSHIFT, True)
            await self.send_key_press(keypress.keycode)
            if keypress.needs_shift:
                await self.send_keycode(KEY_LEFTSHIFT, False)

    async def _create_session(self) -> str:
        token = f"vox_{uuid.uuid4().hex}"
        response, results = await self._portal_request(
            member="CreateSession",
            signature="a{sv}",
            args=[],
            options={"session_handle_token": Variant("s", token)},
        )
        if response != 0:
            raise PortalInputError("Portal session creation rejected")
        session_handle = results.get("session_handle")
        if session_handle is None:
            raise PortalInputError("Portal session handle missing")
        return session_handle.value

    async def _select_devices(self, device_mask: int) -> None:
        response, _results = await self._portal_request(
            member="SelectDevices",
            signature="oa{sv}",
            args=[self._session_handle],
            options={"types": Variant("u", device_mask)},
        )
        if response != 0:
            raise PortalInputError("Portal select devices rejected")

    async def _start_session(self, device_mask: int) -> None:
        response, _results = await self._portal_request(
            member="Start",
            signature="osa{sv}",
            args=[self._session_handle, ""],
            options={"devices": Variant("u", device_mask)},
        )
        if response != 0:
            raise PortalInputError("Portal session start rejected")

    async def _portal_request(
        self,
        member: str,
        signature: str,
        args: list,
        options: dict[str, Variant],
    ) -> tuple[int, dict[str, Variant]]:
        """Call a RemoteDesktop method that answers via a Request Response signal.

        Each call gets a unique handle_token. Without one the portal falls
        back to the fixed token "t", so back-to-back requests collide on the
        same Request object path and the portal never answers. The Response
        handler is registered on the predicted path before calling, so a
        response that arrives immediately can't be missed.
        """
        if not self._bus:
            raise PortalInputError("Portal bus not connected")
        token = f"vox_{uuid.uuid4().hex}"
        sender = self._bus.unique_name.lstrip(":").replace(".", "_")
        request_path = f"{DESKTOP_PATH}/request/{sender}/{token}"

        future: asyncio.Future[tuple[int, dict[str, Variant]]] = (
            asyncio.get_running_loop().create_future()
        )
        handler = _response_handler(request_path, future)
        self._bus.add_message_handler(handler)
        try:
            await self._call(
                path=DESKTOP_PATH,
                interface=REMOTE_DESKTOP_IFACE,
                member=member,
                signature=signature,
                body=[*args, {**options, "handle_token": Variant("s", token)}],
            )
            return await asyncio.wait_for(future, REQUEST_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise PortalInputError(
                f"Timed out after {REQUEST_TIMEOUT:.0f}s waiting for portal {member} response "
                "(permission dialog unanswered?)"
            ) from exc
        finally:
            self._bus.remove_message_handler(handler)

    async def _call(
        self,
        path: str,
        interface: str,
        member: str,
        signature: str,
        body: list,
    ) -> list:
        if not self._bus:
            raise PortalInputError("Portal bus not connected")
        message = Message(
            destination=DESKTOP_SERVICE,
            path=path,
            interface=interface,
            member=member,
            signature=signature,
            body=body,
        )
        reply = await self._bus.call(message)
        if reply.message_type == MessageType.ERROR:
            raise PortalInputError(reply.error_name or "Portal call failed")
        return reply.body


def _response_handler(
    request_path: str,
    future: asyncio.Future[tuple[int, dict[str, Variant]]],
) -> Callable[[Message], bool]:
    """Build a bus message handler that resolves future with a Request's Response."""

    def handler(message: Message) -> bool:
        if message.message_type != MessageType.SIGNAL:
            return False
        if message.path != request_path:
            return False
        if message.interface != REQUEST_IFACE or message.member != "Response":
            return False
        response, results = message.body
        if not future.done():
            future.set_result((response, results))
        return True

    return handler
