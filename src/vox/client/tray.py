"""System tray icon using pystray."""

import logging
import os
import threading
from enum import Enum
from typing import Callable

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Detect Wayland
IS_WAYLAND = os.environ.get("XDG_SESSION_TYPE") == "wayland"

# Check if we can use AppIndicator (required for Wayland/GNOME)
APPINDICATOR_AVAILABLE = False
try:
    import gi
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3
    APPINDICATOR_AVAILABLE = True
    logger.debug("AyatanaAppIndicator3 available")
except (ImportError, ValueError):
    try:
        import gi
        gi.require_version('AppIndicator3', '0.1')
        from gi.repository import AppIndicator3
        APPINDICATOR_AVAILABLE = True
        logger.debug("AppIndicator3 available")
    except (ImportError, ValueError):
        logger.debug("No AppIndicator available")

# Import pystray after checking for AppIndicator
PYSTRAY_AVAILABLE = False
try:
    import pystray
    PYSTRAY_AVAILABLE = True
except ImportError:
    logger.debug("pystray not available")

# On Wayland without AppIndicator, tray won't work - don't even try
TRAY_SUPPORTED = PYSTRAY_AVAILABLE and (not IS_WAYLAND or APPINDICATOR_AVAILABLE)

if IS_WAYLAND and not APPINDICATOR_AVAILABLE:
    logger.debug(
        "Tray icon disabled: Wayland requires AppIndicator. "
        "Install: sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1"
    )


class TrayState(Enum):
    """Tray icon states."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    RECORDING = "recording"


def create_icon_image(state: TrayState, size: int = 64) -> Image.Image:
    """Create an icon image for the given state.

    Args:
        state: The tray state
        size: Icon size in pixels

    Returns:
        PIL Image for the icon
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if state == TrayState.DISCONNECTED:
        color = (128, 128, 128, 255)
    elif state == TrayState.CONNECTED:
        color = (76, 175, 80, 255)
    elif state == TrayState.RECORDING:
        color = (244, 67, 54, 255)
    else:
        color = (128, 128, 128, 255)

    margin = size // 8
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
    )

    inner_margin = size // 4
    inner_color = (255, 255, 255, 200)
    draw.ellipse(
        [inner_margin, inner_margin, size - inner_margin, size - inner_margin],
        fill=inner_color,
    )

    mic_color = color
    mic_x = size // 2
    mic_top = size // 3
    mic_bottom = size * 2 // 3
    mic_width = size // 6

    draw.ellipse(
        [
            mic_x - mic_width,
            mic_top,
            mic_x + mic_width,
            mic_bottom,
        ],
        fill=mic_color,
    )

    return image


class TrayIcon:
    """System tray icon for vox."""

    def __init__(
        self,
        on_open_tui: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the tray icon.

        Args:
            on_open_tui: Callback when "Open TUI" is clicked
            on_quit: Callback when "Quit" is clicked
        """
        self.on_open_tui = on_open_tui
        self.on_quit = on_quit
        self._state = TrayState.DISCONNECTED
        self._icon = None
        self._thread: threading.Thread | None = None
        self._enabled = TRAY_SUPPORTED

    @property
    def state(self) -> TrayState:
        """Get current tray state."""
        return self._state

    def set_state(self, state: TrayState) -> None:
        """Set the tray icon state.

        Args:
            state: New state
        """
        self._state = state
        # Only update if we have a working icon
        if self._icon and self._enabled:
            try:
                self._icon.icon = create_icon_image(state)
                self._icon.title = self._get_title()
            except Exception:
                # Icon failed, disable further updates
                self._enabled = False

    def _get_title(self) -> str:
        """Get title for current state."""
        titles = {
            TrayState.DISCONNECTED: "Vox - Disconnected",
            TrayState.CONNECTED: "Vox - Ready",
            TrayState.RECORDING: "Vox - Recording...",
        }
        return titles.get(self._state, "Vox")

    def _create_menu(self):
        """Create the tray menu."""
        if not PYSTRAY_AVAILABLE:
            return None

        items = []

        if self.on_open_tui:
            items.append(
                pystray.MenuItem("Open TUI", lambda: self.on_open_tui())
            )

        items.append(pystray.MenuItem("Settings", lambda: self._open_settings()))
        items.append(pystray.Menu.SEPARATOR)

        if self.on_quit:
            items.append(pystray.MenuItem("Quit", lambda: self.on_quit()))

        return pystray.Menu(*items)

    def _open_settings(self) -> None:
        """Open settings (placeholder)."""
        logger.info("Settings menu clicked")

    def _run_icon(self) -> None:
        """Run the icon in a thread with error handling."""
        try:
            self._icon.run()
        except Exception as e:
            logger.debug(f"Tray icon stopped: {e}")
            self._enabled = False

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        if not self._enabled:
            return

        if self._icon:
            return

        try:
            self._icon = pystray.Icon(
                name="vox",
                icon=create_icon_image(self._state),
                title=self._get_title(),
                menu=self._create_menu(),
            )

            self._thread = threading.Thread(target=self._run_icon, daemon=True)
            self._thread.start()
            logger.info("Tray icon started")

        except Exception as e:
            logger.debug(f"Failed to create tray icon: {e}")
            self._enabled = False

    def stop(self) -> None:
        """Stop the tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
            logger.debug("Tray icon stopped")

    def __enter__(self) -> "TrayIcon":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


def check_tray_support() -> dict[str, bool]:
    """Check tray icon support on this system.

    Returns:
        Dict with support status for various backends
    """
    return {
        "pystray": PYSTRAY_AVAILABLE,
        "appindicator": APPINDICATOR_AVAILABLE,
        "wayland": IS_WAYLAND,
    }
