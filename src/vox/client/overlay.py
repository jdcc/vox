"""Overlay indicator control via GNOME Shell extension D-Bus interface."""

import logging
from enum import Enum
from typing import Literal

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError

logger = logging.getLogger(__name__)


class OverlayState(Enum):
    """Overlay indicator states."""

    HIDDEN = "hidden"
    RECORDING = "recording"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILURE = "failure"


OverlayPosition = Literal["top-right", "top-center", "bottom-right"]

DBUS_NAME = "org.vox.Extension"
DBUS_PATH = "/org/vox/Extension"


class Overlay:
    """Controls the overlay indicator via GNOME Shell extension D-Bus interface."""

    def __init__(self, position: OverlayPosition = "top-right", enabled: bool = True) -> None:
        """Initialize the overlay controller.

        Args:
            position: Screen position for the overlay (configured in extension settings)
            enabled: Whether overlay is enabled
        """
        self._position = position
        self._enabled = enabled
        self._proxy = None
        self._available = False

    def _get_proxy(self):
        """Get or create the D-Bus proxy."""
        if self._proxy is not None:
            return self._proxy

        try:
            bus = SessionMessageBus()
            self._proxy = bus.get_proxy(DBUS_NAME, DBUS_PATH)
            self._available = True
            return self._proxy
        except DBusError as e:
            logger.debug(f"Failed to connect to D-Bus service: {e}")
            self._available = False
            return None

    @property
    def available(self) -> bool:
        """Check if overlay is available and enabled."""
        if not self._enabled:
            return False
        if self._available:
            return True
        # Try to connect
        self._get_proxy()
        return self._available

    def start(self) -> None:
        """Initialize connection to the extension.

        The GNOME Shell extension runs independently, so we just verify connectivity.
        """
        if not self._enabled:
            return

        proxy = self._get_proxy()
        if proxy is None:
            logger.debug(
                "Vox GNOME Shell extension not available. "
                "Run 'make install-extension' and enable with "
                "'gnome-extensions enable vox@local'"
            )
            return

        logger.debug("Connected to Vox GNOME Shell extension")

    def stop(self) -> None:
        """Cleanup D-Bus connection."""
        # Hide indicator before disconnecting
        if self._proxy is not None:
            try:
                self._proxy.SetState("hidden")
            except Exception:
                pass
        self._proxy = None
        logger.debug("Disconnected from overlay extension")

    def set_state(self, state: OverlayState) -> None:
        """Set the overlay state.

        Args:
            state: New overlay state
        """
        if not self._enabled:
            return

        proxy = self._get_proxy()
        if proxy is None:
            return

        try:
            proxy.SetState(state.value)
            logger.debug(f"Overlay state: {state.value}")
        except DBusError as e:
            logger.debug(f"Failed to set overlay state: {e}")
            self._available = False
            self._proxy = None

    def recording(self) -> None:
        """Show recording indicator."""
        self.set_state(OverlayState.RECORDING)

    def processing(self) -> None:
        """Show processing indicator."""
        self.set_state(OverlayState.PROCESSING)

    def success(self) -> None:
        """Flash success indicator."""
        self.set_state(OverlayState.SUCCESS)

    def failure(self) -> None:
        """Flash failure indicator."""
        self.set_state(OverlayState.FAILURE)

    def hide(self) -> None:
        """Hide the overlay."""
        self.set_state(OverlayState.HIDDEN)

    def __enter__(self) -> "Overlay":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
