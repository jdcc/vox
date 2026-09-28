"""Tests for vox.server.app."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import vox.server.app as app_module
from vox.config import Config
from vox.server.app import AudioStreamState, Server
from vox.server.transcriber import TranscriptionResult


@pytest.mark.asyncio
async def test_handle_message_bytes_chunk(monkeypatch) -> None:
    server = Server(config=Config())
    audio_state = AudioStreamState(active=True)
    handler = AsyncMock()
    monkeypatch.setattr(server, "_handle_audio_chunk", handler)

    await server._handle_message(MagicMock(), b"chunk", audio_state)

    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_message_audio_start(monkeypatch) -> None:
    server = Server(config=Config())
    audio_state = AudioStreamState()
    starter = MagicMock()
    monkeypatch.setattr(server, "_start_audio_stream", starter)

    await server._handle_message(MagicMock(), json.dumps({"type": "AUDIO_START"}), audio_state)

    starter.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_audio_end(monkeypatch) -> None:
    server = Server(config=Config())
    audio_state = AudioStreamState(active=True)
    ender = AsyncMock()
    monkeypatch.setattr(server, "_end_audio_stream", ender)

    await server._handle_message(MagicMock(), json.dumps({"type": "AUDIO_END"}), audio_state)

    ender.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_message_ping() -> None:
    server = Server(config=Config())
    audio_state = AudioStreamState()
    websocket = MagicMock()
    websocket.send = AsyncMock()

    await server._handle_message(websocket, json.dumps({"type": "PING"}), audio_state)

    websocket.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_message_invalid_json() -> None:
    server = Server(config=Config())
    audio_state = AudioStreamState()
    websocket = MagicMock()
    websocket.send = AsyncMock()

    await server._handle_message(websocket, "{bad", audio_state)

    websocket.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_message_unknown_type() -> None:
    server = Server(config=Config())
    audio_state = AudioStreamState()
    websocket = MagicMock()
    websocket.send = AsyncMock()

    await server._handle_message(websocket, json.dumps({"type": "UNKNOWN"}), audio_state)


def test_start_audio_stream_parses_numbers() -> None:
    state = AudioStreamState(active=True)
    server = Server(config=Config())

    server._start_audio_stream(state, {"sample_rate": "48000", "channels": "2"})

    assert state.sample_rate == 48000
    assert state.channels == 2
    assert state.active is True


def test_start_audio_stream_inactive_state() -> None:
    state = AudioStreamState(active=False)
    server = Server(config=Config())

    server._start_audio_stream(state, {"sample_rate": 16000, "channels": 1})

    assert state.active is True


def test_start_audio_stream_defaults() -> None:
    state = AudioStreamState(active=True)
    server = Server(config=Config())

    server._start_audio_stream(state, {"sample_rate": None, "channels": "bad"})

    assert state.sample_rate == 16000
    assert state.channels == 1


def test_start_audio_stream_resets_buffer() -> None:
    state = AudioStreamState(active=True)
    state.buffer.extend(b"old")
    server = Server(config=Config())

    server._start_audio_stream(state, {"sample_rate": 16000, "channels": 1})

    assert state.buffer == bytearray()


@pytest.mark.asyncio
async def test_handle_audio_chunk_inactive() -> None:
    server = Server(config=Config())
    state = AudioStreamState(active=False)

    await server._handle_audio_chunk(MagicMock(), b"data", state)


@pytest.mark.asyncio
async def test_handle_audio_chunk_active() -> None:
    server = Server(config=Config())
    state = AudioStreamState(active=True)

    await server._handle_audio_chunk(MagicMock(), b"data", state)

    assert state.buffer == b"data"


@pytest.mark.asyncio
async def test_end_audio_stream_no_active() -> None:
    server = Server(config=Config())
    state = AudioStreamState(active=False)

    await server._end_audio_stream(MagicMock(), state)


@pytest.mark.asyncio
async def test_end_audio_stream_empty_buffer() -> None:
    server = Server(config=Config())
    state = AudioStreamState(active=True)
    websocket = MagicMock()
    websocket.send = AsyncMock()

    await server._end_audio_stream(websocket, state)

    websocket.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_audio_missing_components() -> None:
    server = Server(config=Config())
    websocket = MagicMock()
    websocket.send = AsyncMock()

    await server._process_audio(websocket, b"data")

    websocket.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_audio_agent_flow(monkeypatch) -> None:
    config = Config()
    server = Server(config=config)
    server.transcriber = MagicMock()
    server.agent = MagicMock()
    server.agent.process = AsyncMock(return_value="final")

    server.transcriber.transcribe_bytes = MagicMock(
        return_value=TranscriptionResult(text="hello")
    )

    websocket = MagicMock()
    websocket.send = AsyncMock()

    async def to_thread_stub(func, *args):
        return func(*args)

    monkeypatch.setattr(asyncio, "to_thread", to_thread_stub)

    await server._process_audio(websocket, b"data")

    assert websocket.send.await_count == 3


@pytest.mark.asyncio
async def test_process_audio_agent_failure_falls_back_to_transcription(monkeypatch) -> None:
    server = Server(config=Config())
    server.transcriber = MagicMock()
    server.agent = MagicMock()
    server.agent.process = AsyncMock(side_effect=RuntimeError("Missing API key"))
    server.transcriber.transcribe_bytes = MagicMock(
        return_value=TranscriptionResult(text="hello, Agent, tidy this up")
    )

    websocket = MagicMock()
    websocket.send = AsyncMock()

    async def to_thread_stub(func, *args):
        return func(*args)

    monkeypatch.setattr(asyncio, "to_thread", to_thread_stub)

    await server._process_audio(websocket, b"data")

    final = json.loads(websocket.send.await_args_list[-1].args[0])
    assert final == {
        "type": "TRANSCRIPTION",
        "text": "hello, Agent, tidy this up",
        "processing": False,
    }


@pytest.mark.asyncio
async def test_process_audio_no_agent_text(monkeypatch) -> None:
    config = Config()
    config.agent.enabled = False
    server = Server(config=config)
    server.transcriber = MagicMock()
    server.agent = MagicMock()
    server.transcriber.transcribe_bytes = MagicMock(
        return_value=TranscriptionResult(text="")
    )

    websocket = MagicMock()
    websocket.send = AsyncMock()

    async def to_thread_stub(func, *args):
        return func(*args)

    monkeypatch.setattr(asyncio, "to_thread", to_thread_stub)

    await server._process_audio(websocket, b"data")

    assert websocket.send.await_count == 2


@pytest.mark.asyncio
async def test_handle_connection_connection_closed(monkeypatch) -> None:
    server = Server(config=Config())

    class FakeClosed(Exception):
        pass

    monkeypatch.setattr(app_module.websockets, "ConnectionClosed", FakeClosed)

    class FakeWebSocket:
        remote_address = ("127.0.0.1", 12345)

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise FakeClosed()

    await server._handle_connection(FakeWebSocket())


@pytest.mark.asyncio
async def test_handle_connection_generic_error(monkeypatch) -> None:
    server = Server(config=Config())

    class FakeWebSocket:
        remote_address = ("127.0.0.1", 12345)

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError("boom")

    await server._handle_connection(FakeWebSocket())


@pytest.mark.asyncio
async def test_handle_connection_message(monkeypatch) -> None:
    server = Server(config=Config())

    class FakeWebSocket:
        remote_address = ("127.0.0.1", 12345)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if hasattr(self, "_done"):
                raise StopAsyncIteration
            self._done = True
            return json.dumps({"type": "PING"})

    handler = AsyncMock()
    monkeypatch.setattr(server, "_handle_message", handler)

    await server._handle_connection(FakeWebSocket())

    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_end_audio_stream_processes(monkeypatch) -> None:
    server = Server(config=Config())
    state = AudioStreamState(active=True)
    state.buffer.extend(b"data")
    state.sample_rate = 44100

    processor = AsyncMock()
    monkeypatch.setattr(server, "_process_audio", processor)

    websocket = MagicMock()
    await server._end_audio_stream(websocket, state)

    processor.assert_awaited_once_with(websocket, b"data", sample_rate=44100)


@pytest.mark.asyncio
async def test_run_server(monkeypatch) -> None:
    runner = AsyncMock()
    monkeypatch.setattr(app_module.Server, "start", runner)

    await app_module.run_server("127.0.0.1", 9999)

    runner.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_server(monkeypatch) -> None:
    server = Server(config=Config())
    transcriber = MagicMock()
    agent = MagicMock()
    agent.warm_up = AsyncMock()
    monkeypatch.setattr(app_module.Transcriber, "from_config", MagicMock(return_value=transcriber))
    monkeypatch.setattr(app_module, "AgentProcessor", MagicMock(return_value=agent))

    ws_server = MagicMock()
    ws_server.wait_closed = AsyncMock()
    serve_mock = AsyncMock(return_value=ws_server)
    monkeypatch.setattr(app_module.websockets, "serve", serve_mock)

    await server.start(host="127.0.0.1", port=9999)
    await server._warmup_task

    serve_mock.assert_awaited_once()
    ws_server.wait_closed.assert_awaited_once()
    agent.warm_up.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_server(monkeypatch) -> None:
    server = Server(config=Config())
    ws_server = MagicMock()
    ws_server.close = MagicMock()
    ws_server.wait_closed = AsyncMock()
    server._server = ws_server

    await server.stop()

    ws_server.close.assert_called_once()
    ws_server.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_server_no_instance() -> None:
    server = Server(config=Config())

    await server.stop()


@pytest.mark.asyncio
async def test_handle_message_exception(monkeypatch) -> None:
    server = Server(config=Config())
    audio_state = AudioStreamState()
    websocket = MagicMock()
    websocket.send = AsyncMock(side_effect=[RuntimeError("boom"), None])

    await server._handle_message(websocket, json.dumps({"type": "PING"}), audio_state)
