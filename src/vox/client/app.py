"""Client application main loop."""

import asyncio
import logging
import signal

from vox.config import Config, load_config
from vox.client.audio import AudioRecorder
from vox.client.connection import ConnectionState, ServerConnection, TranscriptionResponse
from vox.client.hotkey import HotkeyListener, check_input_permissions
from vox.client.output import OutputHandler, check_wayland_tools
from vox.client.overlay import Overlay

logger = logging.getLogger(__name__)


class Client:
    """Vox client application."""

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the client.

        Args:
            config: Application configuration. If None, loads from file.
        """
        self.config = config or load_config()

        self.audio = AudioRecorder()
        self.output = OutputHandler(
            method=self.config.output.method,
            typing_method=self.config.output.typing_method,
        )
        self.connection = ServerConnection(
            host=self.config.server.host,
            port=self.config.server.port,
            on_state_change=self._on_connection_state_change,
            on_transcription=self._on_transcription,
        )
        self.hotkey: HotkeyListener | None = None
        self.overlay = Overlay(
            position=self.config.overlay.position,
            enabled=self.config.overlay.enabled,
        )

        self._running = False
        self._is_recording = False
        self._pending_output: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _on_connection_state_change(self, state: ConnectionState) -> None:
        """Handle connection state changes.

        Args:
            state: New connection state
        """
        if state == ConnectionState.CONNECTED:
            logger.info("Connected to server")
        elif state == ConnectionState.DISCONNECTED:
            logger.info("Disconnected from server")

    def _on_transcription(self, response: TranscriptionResponse) -> None:
        """Handle transcription results.

        Args:
            response: Transcription response
        """
        if response.processing:
            logger.info(f"Transcribed: {response.text} (processing with agent...)")
        else:
            logger.info(f"Final text: {response.text}")
            self._pending_output = response.text
            self.overlay.success()

            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._output_text(response.text),
                    self._loop,
                )

    async def _output_text(self, text: str) -> None:
        """Output text to clipboard/typing.

        Args:
            text: Text to output
        """
        if text:
            await self.output.output(text)

    def _on_hotkey_press(self) -> None:
        """Handle hotkey press (start recording)."""
        if not self._is_recording and self.connection.is_connected:
            self._is_recording = True
            self.overlay.recording()
            self.audio.start_recording()
            logger.info("Recording started")

    def _on_hotkey_release(self) -> None:
        """Handle hotkey release (stop recording and send audio)."""
        if self._is_recording:
            self._is_recording = False
            self.overlay.processing()
            audio_bytes = self.audio.stop_recording()
            logger.info(f"Recording stopped, {len(audio_bytes)} bytes")

            if audio_bytes and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self.connection.send_audio(audio_bytes),
                    self._loop,
                )

    async def start(self) -> None:
        """Start the client."""
        self._loop = asyncio.get_event_loop()

        if not check_input_permissions():
            logger.warning(
                "Not in 'input' group. Hotkeys may not work. "
                "Run: sudo usermod -aG input $USER (then log out/in)"
            )

        tools = check_wayland_tools()
        missing = [t for t, available in tools.items() if not available]
        if missing:
            logger.warning(
                f"Missing Wayland tools: {', '.join(missing)}. "
                "Install with: sudo apt install wl-clipboard wtype"
            )

        self.overlay.start()

        await self.connection.start()

        self.hotkey = HotkeyListener(
            hotkey=self.config.hotkey.trigger,
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
        )

        try:
            await self.hotkey.start()
        except RuntimeError as e:
            logger.error(f"Failed to start hotkey listener: {e}")
            return

        self._running = True

        logger.info(
            f"Client started. Hold {self.config.hotkey.trigger} to record. "
            f"Connected to {self.config.server.host}:{self.config.server.port}"
        )

        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the client."""
        self._running = False

        if self.hotkey:
            await self.hotkey.stop()

        await self.connection.disconnect()
        self.audio.close()
        self.overlay.stop()

        logger.info("Client stopped")


async def run_client() -> None:
    """Run the client application."""
    client = Client()

    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(client.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await client.start()
    finally:
        await client.stop()
