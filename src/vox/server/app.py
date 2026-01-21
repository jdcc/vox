"""Server application with WebSocket handling."""

import asyncio
import json
import logging
from dataclasses import dataclass, field

import websockets
from websockets.server import WebSocketServerProtocol

from vox.config import Config, load_config
from vox.server.agent import AgentProcessor
from vox.server.transcriber import Transcriber

logger = logging.getLogger(__name__)


@dataclass
class ServerState:
    """Server state."""

    transcriber: Transcriber
    agent: AgentProcessor
    config: Config


@dataclass
class AudioStreamState:
    """Per-connection audio streaming state."""

    buffer: bytearray = field(default_factory=bytearray)
    sample_rate: int = 16000
    channels: int = 1
    active: bool = False


class Server:
    """WebSocket server for speech-to-text."""

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the server.

        Args:
            config: Application configuration. If None, loads from file.
        """
        self.config = config or load_config()
        self.transcriber: Transcriber | None = None
        self.agent: AgentProcessor | None = None
        self._server: websockets.WebSocketServer | None = None

    async def start(self, host: str | None = None, port: int | None = None) -> None:
        """Start the server.

        Args:
            host: Host to bind to (overrides config)
            port: Port to bind to (overrides config)
        """
        host = host or self.config.server.host
        port = port or self.config.server.port

        logger.info("Initializing transcriber...")
        self.transcriber = Transcriber.from_config(self.config)

        logger.info("Initializing agent processor...")
        self.agent = AgentProcessor(self.config)

        logger.info(f"Starting server on {host}:{port}")

        self._server = await websockets.serve(
            self._handle_connection,
            host,
            port,
            ping_interval=30,
            ping_timeout=10,
        )

        logger.info(f"Server listening on ws://{host}:{port}")

        await self._server.wait_closed()

    async def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Server stopped")

    async def _handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a WebSocket connection.

        Args:
            websocket: The WebSocket connection
        """
        client_addr = websocket.remote_address
        logger.info(f"Client connected: {client_addr}")

        audio_state = AudioStreamState()

        try:
            async for message in websocket:
                await self._handle_message(websocket, message, audio_state)
        except websockets.ConnectionClosed:
            logger.info(f"Client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}")

    async def _handle_message(
        self,
        websocket: WebSocketServerProtocol,
        message: str | bytes,
        audio_state: AudioStreamState,
    ) -> None:
        """Handle a message from a client.

        Args:
            websocket: The WebSocket connection
            message: The message received
            audio_state: Per-connection audio streaming state
        """
        try:
            if isinstance(message, bytes):
                await self._handle_audio_chunk(websocket, message, audio_state)
                return

            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "AUDIO_START":
                self._start_audio_stream(audio_state, data)
            elif msg_type == "AUDIO_END":
                await self._end_audio_stream(websocket, audio_state)
            elif msg_type == "PING":
                await websocket.send(json.dumps({"type": "PONG"}))
            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            logger.error("Invalid JSON message")
            await websocket.send(
                json.dumps({"type": "ERROR", "error": "Invalid JSON"})
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await websocket.send(
                json.dumps({"type": "ERROR", "error": str(e)})
            )

    def _start_audio_stream(self, audio_state: AudioStreamState, data: dict) -> None:
        """Initialize streaming state for a new audio upload."""
        if audio_state.active:
            logger.warning("Audio stream already active; resetting buffer")

        audio_state.buffer.clear()
        sample_rate = data.get("sample_rate", 16000)
        channels = data.get("channels", 1)
        try:
            audio_state.sample_rate = int(sample_rate)
        except (TypeError, ValueError):
            audio_state.sample_rate = 16000
        try:
            audio_state.channels = int(channels)
        except (TypeError, ValueError):
            audio_state.channels = 1
        audio_state.active = True

    async def _handle_audio_chunk(
        self,
        _websocket: WebSocketServerProtocol,
        chunk: bytes,
        audio_state: AudioStreamState,
    ) -> None:
        """Handle a binary audio chunk."""
        if not audio_state.active:
            logger.warning("Received audio chunk without active stream")
            return

        audio_state.buffer.extend(chunk)

    async def _end_audio_stream(
        self,
        websocket: WebSocketServerProtocol,
        audio_state: AudioStreamState,
    ) -> None:
        """Finalize streaming and process the audio."""
        if not audio_state.active:
            logger.warning("Received AUDIO_END without active stream")
            return

        audio_state.active = False

        if not audio_state.buffer:
            await websocket.send(
                json.dumps({"type": "ERROR", "error": "No audio data"})
            )
            return

        audio_bytes = bytes(audio_state.buffer)
        audio_state.buffer.clear()

        await self._process_audio(
            websocket,
            audio_bytes,
            sample_rate=audio_state.sample_rate,
        )

    async def _process_audio(
        self,
        websocket: WebSocketServerProtocol,
        audio_bytes: bytes,
        sample_rate: int = 16000,
    ) -> None:
        """Transcribe audio and send responses."""
        if self.transcriber is None or self.agent is None:
            await websocket.send(
                json.dumps({"type": "ERROR", "error": "Server not initialized"})
            )
            return

        logger.info(f"Received {len(audio_bytes)} bytes of audio")

        await websocket.send(json.dumps({"type": "PROCESSING"}))

        result = await asyncio.to_thread(
            self.transcriber.transcribe_bytes,
            audio_bytes,
            sample_rate,
        )

        logger.info(f"Transcribed: {result.text}")

        if self.config.agent.enabled and result.text:
            await websocket.send(
                json.dumps({
                    "type": "TRANSCRIPTION",
                    "text": result.text,
                    "processing": True,
                })
            )

            final_text = await self.agent.process(result.text)

            await websocket.send(
                json.dumps({
                    "type": "TRANSCRIPTION",
                    "text": final_text,
                    "processing": False,
                })
            )
        else:
            await websocket.send(
                json.dumps({
                    "type": "TRANSCRIPTION",
                    "text": result.text,
                    "processing": False,
                })
            )


async def run_server(host: str | None = None, port: int | None = None) -> None:
    """Run the server.

    Args:
        host: Host to bind to
        port: Port to bind to
    """
    server = Server()
    await server.start(host, port)
