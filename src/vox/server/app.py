"""Server application with WebSocket handling."""

import asyncio
import base64
import json
import logging
from dataclasses import dataclass

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

        try:
            async for message in websocket:
                await self._handle_message(websocket, message)
        except websockets.ConnectionClosed:
            logger.info(f"Client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}")

    async def _handle_message(
        self,
        websocket: WebSocketServerProtocol,
        message: str | bytes,
    ) -> None:
        """Handle a message from a client.

        Args:
            websocket: The WebSocket connection
            message: The message received
        """
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "AUDIO":
                await self._handle_audio(websocket, data)
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

    async def _handle_audio(
        self,
        websocket: WebSocketServerProtocol,
        data: dict,
    ) -> None:
        """Handle audio transcription request.

        Args:
            websocket: The WebSocket connection
            data: The message data containing audio
        """
        if self.transcriber is None or self.agent is None:
            await websocket.send(
                json.dumps({"type": "ERROR", "error": "Server not initialized"})
            )
            return

        audio_b64 = data.get("audio")
        if not audio_b64:
            await websocket.send(
                json.dumps({"type": "ERROR", "error": "No audio data"})
            )
            return

        audio_bytes = base64.b64decode(audio_b64)

        logger.info(f"Received {len(audio_bytes)} bytes of audio")

        await websocket.send(json.dumps({"type": "PROCESSING"}))

        result = await asyncio.to_thread(
            self.transcriber.transcribe_bytes, audio_bytes
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
