"""Global hotkey handling via GNOME Shell extension D-Bus signals."""

import logging
from typing import Callable

from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

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
        self._bus = None
        self._interface = None

    async def start(self) -> None:
        """Start listening for hotkey signals from the GNOME extension."""
        try:
            self._bus = await MessageBus().connect()
            introspection = await self._bus.introspect(DBUS_NAME, DBUS_PATH)
            proxy = self._bus.get_proxy_object(DBUS_NAME, DBUS_PATH, introspection)
            self._interface = proxy.get_interface(DBUS_INTERFACE)
        except DBusError as e:
            raise RuntimeError(
                f"Failed to connect to Vox GNOME Shell extension: {e}\n"
                "Make sure the extension is installed and enabled:\n"
                "  make install-extension\n"
                "  gnome-extensions enable vox@local\n"
                "Then restart GNOME Shell (log out/in on Wayland)"
            ) from e

        # Subscribe to D-Bus signals - dbus-next handles event loop integration natively
        self._interface.on_hotkey_pressed(self._on_hotkey_pressed_signal)
        self._interface.on_hotkey_released(self._on_hotkey_released_signal)

        self._running = True
        logger.info(f"Listening for hotkey signals from GNOME extension (hotkey: {self._hotkey})")

    def _on_hotkey_pressed_signal(self) -> None:
        """Handle HotkeyPressed signal from D-Bus."""
        logger.debug("Hotkey pressed (D-Bus signal)")
        try:
            self.on_press()
        except Exception as e:
            logger.error(f"Error in hotkey press handler: {e}")

    def _on_hotkey_released_signal(self) -> None:
        """Handle HotkeyReleased signal from D-Bus."""
        logger.debug("Hotkey released (D-Bus signal)")
        try:
            self.on_release()
        except Exception as e:
            logger.error(f"Error in hotkey release handler: {e}")

    async def stop(self) -> None:
        """Stop listening for hotkey signals."""
        self._running = False

        if self._bus:
            self._bus.disconnect()
            self._bus = None

        self._interface = None
        logger.info("Hotkey listener stopped")


async def check_extension_available() -> bool:
    """Check if the Vox GNOME Shell extension is available and running.

    Returns:
        True if extension is available
    """
    try:
        bus = await MessageBus().connect()
        introspection = await bus.introspect(DBUS_NAME, DBUS_PATH)
        proxy = bus.get_proxy_object(DBUS_NAME, DBUS_PATH, introspection)
        interface = proxy.get_interface(DBUS_INTERFACE)
        # Try to call GetState to verify the extension is responsive
        await interface.call_get_state()
        bus.disconnect()
        return True
    except DBusError:
        return False
    except Exception as e:
        logger.debug(f"Error checking extension: {e}")
        return False


def check_input_permissions() -> bool:
    """Check if user is in the input group for device access.

    Returns:
        True if user belongs to the input group
    """
    import grp
    import os

    try:
        input_gid = grp.getgrnam("input").gr_gid
    except KeyError:
        return False

    return input_gid in os.getgroups()
