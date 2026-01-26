"""Overlay indicator control via GNOME Shell extension D-Bus interface."""

import asyncio
import logging
from enum import Enum
from typing import Literal

from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

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
DBUS_INTERFACE = "org.vox.Extension"


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
        self._bus = None
        self._interface = None
        self._available = False
        self._loop = None

    async def _connect(self) -> bool:
        """Connect to the D-Bus service."""
        if self._interface is not None:
            return True

        try:
            self._bus = await MessageBus().connect()
            introspection = await self._bus.introspect(DBUS_NAME, DBUS_PATH)
            proxy = self._bus.get_proxy_object(DBUS_NAME, DBUS_PATH, introspection)
            self._interface = proxy.get_interface(DBUS_INTERFACE)
            self._available = True
            return True
        except DBusError as e:
            logger.debug(f"Failed to connect to D-Bus service: {e}")
            self._available = False
            return False

    @property
    def available(self) -> bool:
        """Check if overlay is available and enabled."""
        if not self._enabled:
            return False
        return self._available

    async def start(self) -> None:
        """Initialize connection to the extension.

        The GNOME Shell extension runs independently, so we just verify connectivity.
        """
        if not self._enabled:
            return

        self._loop = asyncio.get_event_loop()

        if not await self._connect():
            logger.debug(
                "Vox GNOME Shell extension not available. "
                "Run 'make install-extension' and enable with "
                "'gnome-extensions enable vox@local'"
            )
            return

        logger.debug("Connected to Vox GNOME Shell extension")

    async def stop(self) -> None:
        """Cleanup D-Bus connection."""
        # Hide indicator before disconnecting
        if self._interface is not None:
            try:
                await self._interface.call_set_state("hidden")
            except Exception:
                pass

        if self._bus:
            self._bus.disconnect()
            self._bus = None

        self._interface = None
        logger.debug("Disconnected from overlay extension")

    async def _set_state_async(self, state: OverlayState) -> None:
        """Set the overlay state asynchronously.

        Args:
            state: New overlay state
        """
        if not self._enabled or self._interface is None:
            return

        try:
            await self._interface.call_set_state(state.value)
            logger.debug(f"Overlay state: {state.value}")
        except DBusError as e:
            logger.debug(f"Failed to set overlay state: {e}")
            self._available = False
            self._interface = None

    async def _set_audio_level_async(self, level: float) -> None:
        """Set the overlay audio level asynchronously.

        Args:
            level: Audio level in the range [0, 1]
        """
        if not self._enabled or self._interface is None:
            return

        try:
            await self._interface.call_set_audio_level(float(level))
        except DBusError as e:
            logger.debug(f"Failed to set overlay audio level: {e}")
            self._available = False
            self._interface = None

    def set_state(self, state: OverlayState) -> None:
        """Set the overlay state.

        Args:
            state: New overlay state
        """
        if not self._enabled or self._interface is None:
            return

        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._set_state_async(state), self._loop)

    def set_audio_level(self, level: float) -> None:
        """Set the overlay audio level.

        Args:
            level: Audio level in the range [0, 1]
        """
        if not self._enabled or self._interface is None or self._loop is None:
            return

        asyncio.run_coroutine_threadsafe(self._set_audio_level_async(level), self._loop)

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

    async def __aenter__(self) -> "Overlay":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
