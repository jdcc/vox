"""Output handling for clipboard and text insertion."""

import asyncio
import logging
import subprocess
from typing import Literal

logger = logging.getLogger(__name__)


class OutputHandler:
    """Handles outputting text via clipboard and/or typing."""

    def __init__(
        self,
        method: Literal["clipboard", "type", "both"] = "both",
        typing_method: Literal["paste", "type"] = "paste",
    ) -> None:
        """Initialize the output handler.

        Args:
            method: Output method (clipboard, type, or both)
            typing_method: How to type text (paste via Ctrl+V or direct typing)
        """
        self.method = method
        self.typing_method = typing_method

    async def output(self, text: str) -> None:
        """Output text using configured method.

        Args:
            text: Text to output
        """
        if not text:
            return

        if self.method in ("clipboard", "both"):
            await self._copy_to_clipboard(text)

        if self.method in ("type", "both"):
            # Small delay to ensure clipboard is ready
            await asyncio.sleep(0.1)

            if self.typing_method == "paste":
                await self._paste()
            else:
                await self._type_text(text)

    async def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard using wl-copy.

        Args:
            text: Text to copy
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "wl-copy",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(input=text.encode("utf-8"))

            if process.returncode == 0:
                logger.debug(f"Copied to clipboard: {text[:50]}...")
            else:
                logger.error(f"wl-copy failed: {stderr.decode()}")

        except FileNotFoundError:
            logger.error("wl-copy not found. Install with: sudo apt install wl-clipboard")
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")

    async def _paste(self) -> None:
        """Paste from clipboard using ydotool to simulate Ctrl+V."""
        try:
            # ydotool key format: key codes separated by space
            # 29 = KEY_LEFTCTRL, 47 = KEY_V
            # Format: keycode:state (1=down, 0=up)
            process = await asyncio.create_subprocess_exec(
                "ydotool",
                "key",
                "29:1",  # Ctrl down
                "47:1",  # V down
                "47:0",  # V up
                "29:0",  # Ctrl up
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                if "ydotoold" in error_msg.lower() or "socket" in error_msg.lower():
                    logger.error(
                        "ydotool paste failed: ydotoold daemon not running. "
                        "Start it with: systemctl --user enable --now ydotool"
                    )
                else:
                    logger.error(f"ydotool paste failed: {error_msg}")

        except FileNotFoundError:
            logger.error("ydotool not found. Install with: sudo apt install ydotool")
        except Exception as e:
            logger.error(f"Error pasting: {e}")

    async def _type_text(self, text: str) -> None:
        """Type text directly using ydotool.

        Args:
            text: Text to type
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "ydotool",
                "type",
                "--",
                text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                if "ydotoold" in error_msg.lower() or "socket" in error_msg.lower():
                    logger.error(
                        "ydotool type failed: ydotoold daemon not running. "
                        "Start it with: systemctl --user enable --now ydotool"
                    )
                else:
                    logger.error(f"ydotool type failed: {error_msg}")

        except FileNotFoundError:
            logger.error("ydotool not found. Install with: sudo apt install ydotool")
        except Exception as e:
            logger.error(f"Error typing text: {e}")


def check_wayland_tools() -> dict[str, bool]:
    """Check if required Wayland tools are installed.

    Returns:
        Dict mapping tool name to availability
    """
    tools = {}

    for tool in ["wl-copy", "wl-paste", "ydotool"]:
        try:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                text=True,
            )
            tools[tool] = result.returncode == 0
        except Exception:
            tools[tool] = False

    return tools


def check_ydotool_daemon() -> bool:
    """Check if ydotool can work (has uinput access or daemon running).

    Returns:
        True if ydotool should work
    """
    import os

    # Check if /dev/uinput is accessible (for ydotool v0.1.x)
    if os.access("/dev/uinput", os.W_OK):
        return True

    # Check for ydotoold socket (for ydotool v1.x)
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if xdg_runtime:
        socket_path = f"{xdg_runtime}/.ydotool_socket"
        if os.path.exists(socket_path):
            return True
    if os.path.exists("/tmp/.ydotool_socket"):
        return True

    return False
