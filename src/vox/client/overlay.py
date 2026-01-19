"""Overlay indicator control via vox-overlay binary."""

import logging
import subprocess
import shutil
from enum import Enum
from typing import Literal

logger = logging.getLogger(__name__)


class OverlayState(Enum):
    """Overlay indicator states."""

    HIDDEN = "hide"
    RECORDING = "recording"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILURE = "failure"


OverlayPosition = Literal["top-right", "top-center", "bottom-right"]


class Overlay:
    """Controls the vox-overlay indicator binary."""

    BINARY_NAME = "vox-overlay"

    def __init__(self, position: OverlayPosition = "top-right", enabled: bool = True) -> None:
        """Initialize the overlay controller.

        Args:
            position: Screen position for the overlay
            enabled: Whether overlay is enabled
        """
        self._position = position
        self._enabled = enabled
        self._process: subprocess.Popen | None = None
        self._available = self._check_binary()

    def _check_binary(self) -> bool:
        """Check if the overlay binary is available."""
        return shutil.which(self.BINARY_NAME) is not None

    @property
    def available(self) -> bool:
        """Check if overlay is available and enabled."""
        return self._enabled and self._available

    def start(self) -> None:
        """Start the overlay process."""
        if not self.available:
            if self._enabled and not self._available:
                logger.debug(
                    f"{self.BINARY_NAME} not found in PATH. "
                    "Run 'make build-overlay install-overlay' to install."
                )
            return

        if self._process is not None:
            return

        try:
            self._process = subprocess.Popen(
                [self.BINARY_NAME, "--position", self._position],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug(f"Started overlay process (pid={self._process.pid})")
        except Exception as e:
            logger.warning(f"Failed to start overlay: {e}")
            self._available = False

    def stop(self) -> None:
        """Stop the overlay process."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            logger.debug("Stopped overlay process")

    def set_state(self, state: OverlayState) -> None:
        """Set the overlay state.

        Args:
            state: New overlay state
        """
        if not self.available or self._process is None:
            return

        if self._process.poll() is not None:
            # Process has exited, try to restart
            self._process = None
            self.start()
            if self._process is None:
                return

        try:
            command = f"{state.value}\n"
            self._process.stdin.write(command.encode())
            self._process.stdin.flush()
            logger.debug(f"Overlay state: {state.value}")
        except Exception as e:
            logger.debug(f"Failed to send overlay command: {e}")
            self._available = False

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
