"""Global hotkey handling via GNOME Shell extension D-Bus signals."""

import asyncio
import logging
from typing import Callable

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from dasbus.loop import EventLoop

logger = logging.getLogger(__name__)

DBUS_NAME = "org.vox.Extension"
DBUS_PATH = "/org/vox/Extension"
DBUS_INTERFACE = "org.vox.Extension"


class HotkeyListener:
    """Listens for global hotkeys via GNOME Shell extension D-Bus signals."""

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        """Initialize the hotkey listener.

        Args:
            hotkey: Hotkey string (e.g., "ctrl+space") - configured in extension settings
            on_press: Callback when hotkey is pressed
            on_release: Callback when hotkey is released
        """
        self._hotkey = hotkey
        self.on_press = on_press
        self.on_release = on_release
        self._running = False
        self._proxy = None
        self._bus = None
        self._event_loop = None
        self._loop_task = None
        self._press_subscription = None
        self._release_subscription = None

    async def start(self) -> None:
        """Start listening for hotkey signals from the GNOME extension."""
        try:
            self._bus = SessionMessageBus()
            self._proxy = self._bus.get_proxy(DBUS_NAME, DBUS_PATH)
        except DBusError as e:
            raise RuntimeError(
                f"Failed to connect to Vox GNOME Shell extension: {e}\n"
                "Make sure the extension is installed and enabled:\n"
                "  make install-extension\n"
                "  gnome-extensions enable vox@local\n"
                "Then restart GNOME Shell (log out/in on Wayland)"
            ) from e

        # Subscribe to D-Bus signals
        connection = self._bus.connection

        self._press_subscription = connection.signal_subscribe(
            DBUS_NAME,
            DBUS_INTERFACE,
            "HotkeyPressed",
            DBUS_PATH,
            None,
            0,
            self._on_hotkey_pressed_signal,
        )

        self._release_subscription = connection.signal_subscribe(
            DBUS_NAME,
            DBUS_INTERFACE,
            "HotkeyReleased",
            DBUS_PATH,
            None,
            0,
            self._on_hotkey_released_signal,
        )

        self._running = True

        # Run the GLib event loop in a thread to process D-Bus signals
        self._event_loop = EventLoop()
        self._loop_task = asyncio.create_task(self._run_event_loop())

        logger.info(f"Listening for hotkey signals from GNOME extension (configured: {self._hotkey})")

    async def _run_event_loop(self) -> None:
        """Run the GLib event loop to process D-Bus signals."""
        import gi
        gi.require_version('GLib', '2.0')
        from gi.repository import GLib

        loop = GLib.MainLoop()
        context = loop.get_context()

        while self._running:
            # Process pending events without blocking
            while context.pending():
                context.iteration(False)
            # Yield to asyncio
            await asyncio.sleep(0.01)

    def _on_hotkey_pressed_signal(self, connection, sender, path, interface, signal, params):
        """Handle HotkeyPressed signal from D-Bus."""
        logger.debug("Hotkey pressed (D-Bus signal)")
        try:
            self.on_press()
        except Exception as e:
            logger.error(f"Error in hotkey press handler: {e}")

    def _on_hotkey_released_signal(self, connection, sender, path, interface, signal, params):
        """Handle HotkeyReleased signal from D-Bus."""
        logger.debug("Hotkey released (D-Bus signal)")
        try:
            self.on_release()
        except Exception as e:
            logger.error(f"Error in hotkey release handler: {e}")

    async def stop(self) -> None:
        """Stop listening for hotkey signals."""
        self._running = False

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        if self._bus and self._bus.connection:
            connection = self._bus.connection
            if self._press_subscription is not None:
                connection.signal_unsubscribe(self._press_subscription)
                self._press_subscription = None
            if self._release_subscription is not None:
                connection.signal_unsubscribe(self._release_subscription)
                self._release_subscription = None

        self._proxy = None
        self._bus = None
        logger.info("Hotkey listener stopped")


def check_extension_available() -> bool:
    """Check if the Vox GNOME Shell extension is available and running.

    Returns:
        True if extension is available
    """
    try:
        bus = SessionMessageBus()
        proxy = bus.get_proxy(DBUS_NAME, DBUS_PATH)
        # Try to call GetState to verify the extension is responsive
        proxy.GetState()
        return True
    except DBusError:
        return False
    except Exception as e:
        logger.debug(f"Error checking extension: {e}")
        return False
