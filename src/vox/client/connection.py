"""WebSocket client connection to server."""

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


@dataclass
class TranscriptionResponse:
    """Response from transcription request."""

    text: str
    processing: bool = False


class ServerConnection:
    """WebSocket connection to the vox server."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9876,
        on_state_change: Callable[[ConnectionState], None] | None = None,
        on_transcription: Callable[[TranscriptionResponse], None] | None = None,
    ) -> None:
        """Initialize the server connection.

        Args:
            host: Server host
            port: Server port
            on_state_change: Callback for connection state changes
            on_transcription: Callback for transcription results
        """
        self.host = host
        self.port = port
        self.on_state_change = on_state_change
        self.on_transcription = on_transcription

        self._ws: WebSocketClientProtocol | None = None
        self._state = ConnectionState.DISCONNECTED
        self._reconnect_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._running = False

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._state == ConnectionState.CONNECTED

    def _set_state(self, state: ConnectionState) -> None:
        """Set connection state and notify callback.

        Args:
            state: New connection state
        """
        if self._state != state:
            self._state = state
            logger.info(f"Connection state: {state.value}")
            if self.on_state_change:
                self.on_state_change(state)

    async def connect(self) -> bool:
        """Connect to the server.

        Returns:
            True if connection successful
        """
        if self._state == ConnectionState.CONNECTED:
            return True

        self._set_state(ConnectionState.CONNECTING)

        uri = f"ws://{self.host}:{self.port}"
        logger.info(f"Connecting to {uri}")

        try:
            self._ws = await websockets.connect(
                uri,
                ping_interval=20,
                ping_timeout=10,
            )
            self._set_state(ConnectionState.CONNECTED)
            logger.info("Connected to server")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._set_state(ConnectionState.DISCONNECTED)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        self._running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._set_state(ConnectionState.DISCONNECTED)

    async def _receive_loop(self) -> None:
        """Loop to receive messages from server."""
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                await self._handle_message(message)

            except websockets.ConnectionClosed:
                logger.info("Connection closed")
                self._set_state(ConnectionState.DISCONNECTED)
                if self._running:
                    asyncio.create_task(self._reconnect())
                break

            except Exception as e:
                logger.error(f"Error receiving message: {e}")

    async def _handle_message(self, message: str | bytes) -> None:
        """Handle a message from the server.

        Args:
            message: The message received
        """
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "TRANSCRIPTION":
                response = TranscriptionResponse(
                    text=data.get("text", ""),
                    processing=data.get("processing", False),
                )
                if self.on_transcription:
                    self.on_transcription(response)

            elif msg_type == "PROCESSING":
                logger.debug("Server is processing audio")

            elif msg_type == "ERROR":
                logger.error(f"Server error: {data.get('error')}")

            elif msg_type == "PONG":
                logger.debug("Received pong")

        except json.JSONDecodeError:
            logger.error("Invalid JSON from server")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _reconnect(self, delay: float = 2.0) -> None:
        """Attempt to reconnect to server.

        Args:
            delay: Delay between reconnection attempts
        """
        while self._running and self._state != ConnectionState.CONNECTED:
            logger.info(f"Reconnecting in {delay}s...")
            await asyncio.sleep(delay)

            if await self.connect():
                self._receive_task = asyncio.create_task(self._receive_loop())
                break

            delay = min(delay * 1.5, 30)

    async def start(self) -> None:
        """Start the connection with automatic reconnection."""
        self._running = True

        if await self.connect():
            self._receive_task = asyncio.create_task(self._receive_loop())
        else:
            self._reconnect_task = asyncio.create_task(self._reconnect())

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send audio data to server for transcription.

        Args:
            audio_bytes: Raw PCM audio bytes
        """
        if not self._ws or self._state != ConnectionState.CONNECTED:
            logger.warning("Not connected to server")
            return

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        message = json.dumps({
            "type": "AUDIO",
            "audio": audio_b64,
        })

        try:
            await self._ws.send(message)
            logger.debug(f"Sent {len(audio_bytes)} bytes of audio")
        except Exception as e:
            logger.error(f"Error sending audio: {e}")

    async def ping(self) -> bool:
        """Send a ping to the server.

        Returns:
            True if ping was sent successfully
        """
        if not self._ws or self._state != ConnectionState.CONNECTED:
            return False

        try:
            await self._ws.send(json.dumps({"type": "PING"}))
            return True
        except Exception:
            return False
