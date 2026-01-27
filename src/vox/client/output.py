"""Output handling for clipboard and text insertion."""

import asyncio
import logging
import os
import subprocess
import shutil
from typing import Literal

from vox.client.portal_input import PortalInput, PortalInputError

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
        self._portal_input: PortalInput | None = None

    async def start(self) -> None:
        """Start portal input once for the client lifetime."""
        if self.method not in ("type", "both"):
            return
        if os.environ.get("XDG_SESSION_TYPE") != "wayland":
            return
        if self._portal_input and self._portal_input.active:
            return
        self._portal_input = PortalInput()
        try:
            await self._portal_input.start()
        except Exception as exc:
            logger.warning("Portal input unavailable: %s", exc)
            self._portal_input = None

    async def stop(self) -> None:
        """Stop portal input session."""
        if self._portal_input:
            await self._portal_input.stop()
            self._portal_input = None

    async def _reinitialize_portal(self) -> bool:
        """Reinitialize the portal session after an error.

        Returns:
            True if reinitialization succeeded, False otherwise.
        """
        logger.info("Reinitializing portal session...")
        if self._portal_input:
            try:
                await self._portal_input.stop()
            except Exception as exc:
                logger.debug("Error stopping portal during reinit: %s", exc)
            self._portal_input = None

        self._portal_input = PortalInput()
        try:
            await self._portal_input.start()
            logger.info("Portal session reinitialized successfully")
            return True
        except Exception as exc:
            logger.warning("Portal reinitialization failed: %s", exc)
            self._portal_input = None
            return False

    async def output(self, text: str) -> None:
        """Output text using configured method.

        Args:
            text: Text to output
        """
        if not text:
            return

        did_copy = False
        if self.method in ("clipboard", "both"):
            logger.debug("Copying text to clipboard")
            await self._copy_to_clipboard(text)
            did_copy = True
            logger.debug("Copied")

        if self.method in ("type", "both"):
            # Small delay to ensure clipboard is ready
            await asyncio.sleep(0.1)

            if self.typing_method == "paste":
                if not did_copy:
                    await self._copy_to_clipboard(text)
                ready = await self._wait_for_clipboard(text)
                if not ready:
                    await self._copy_to_clipboard(text)
                    await self._wait_for_clipboard(text, timeout=0.5)
                await self._paste()
            else:
                await self._type_text(text)

    async def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard using wl-copy.

        Args:
            text: Text to copy
        """
        await asyncio.to_thread(self._copy_to_clipboard_sync, text)

    @staticmethod
    def _copy_to_clipboard_sync(text: str) -> None:
        process = subprocess.Popen(
            ["wl-copy"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        if process.stdin is None:
            logger.error("wl-copy stdin unavailable")
            return

        try:
            process.stdin.write(text)
            process.stdin.close()
        except Exception as exc:
            logger.error("Failed writing to wl-copy stdin: %s", exc)
            return

        try:
            process.wait(timeout=0.05)
        except subprocess.TimeoutExpired:
            logger.debug("Copied to clipboard: %s...", text[:50])
            return

        if process.returncode != 0:
            err = process.stderr.read()
            logger.error("Error copying to clipboard: %s", err)

    async def _paste(self) -> None:
        """Paste from clipboard using portal input."""
        if not self._portal_input or not self._portal_input.active:
            logger.error("Portal input not available for paste.")
            return
        try:
            await self._portal_input.send_paste()
        except (PortalInputError, Exception) as exc:
            logger.warning("Portal paste failed, attempting reinit: %s", exc)
            if await self._reinitialize_portal():
                try:
                    await self._portal_input.send_paste()
                except Exception as retry_exc:
                    logger.error("Portal paste failed after reinit: %s", retry_exc)
            else:
                logger.error("Portal paste failed and reinit unsuccessful")

    async def _wait_for_clipboard(self, text: str, timeout: float = 2.0) -> bool:
        """Wait briefly for clipboard to match expected text."""
        if not shutil.which("wl-paste"):
            return True

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                process = await asyncio.create_subprocess_exec(
                    "wl-paste",
                    "--no-newline",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _stderr = await asyncio.wait_for(
                    process.communicate(), timeout=0.2
                )
                if stdout.decode("utf-8", errors="replace") == text:
                    return True
            except (asyncio.TimeoutError, FileNotFoundError):
                pass

            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(0.05)

    async def _type_text(self, text: str) -> None:
        """Type text directly using portal input.

        Args:
            text: Text to type
        """
        if not self._portal_input or not self._portal_input.active:
            logger.error("Portal input not available for typing.")
            return
        try:
            await self._portal_input.type_text(text)
        except (PortalInputError, Exception) as exc:
            logger.warning("Portal type failed, attempting reinit: %s", exc)
            if await self._reinitialize_portal():
                try:
                    await self._portal_input.type_text(text)
                except Exception as retry_exc:
                    logger.error("Portal type failed after reinit: %s", retry_exc)
            else:
                logger.error("Portal type failed and reinit unsuccessful")


def check_wayland_tools() -> dict[str, bool]:
    """Check if required Wayland tools are installed.

    Returns:
        Dict mapping tool name to availability
    """
    tools = {}

    for tool in ["wl-copy", "wl-paste"]:
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
