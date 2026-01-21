"""Tests for vox.client.connection."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets

from vox.client.connection import ConnectionState, ServerConnection


@pytest.mark.asyncio
async def test_connect_success(monkeypatch, mock_websocket) -> None:
    async def connect_stub(*_args, **_kwargs):
        return mock_websocket

    monkeypatch.setattr(websockets, "connect", connect_stub)

    changes = []

    def on_state(state):
        changes.append(state)

    connection = ServerConnection(on_state_change=on_state)

    assert await connection.connect() is True
    assert connection.is_connected is True
    assert ConnectionState.CONNECTING in changes
    assert ConnectionState.CONNECTED in changes


@pytest.mark.asyncio
async def test_connect_failure(monkeypatch) -> None:
    async def connect_stub(*_args, **_kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(websockets, "connect", connect_stub)

    connection = ServerConnection()
    assert await connection.connect() is False
    assert connection.state == ConnectionState.DISCONNECTED


@pytest.mark.asyncio
async def test_connect_already_connected(monkeypatch) -> None:
    connection = ServerConnection()
    connection._state = ConnectionState.CONNECTED

    connector = AsyncMock()
    monkeypatch.setattr(websockets, "connect", connector)

    assert await connection.connect() is True
    connector.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_cleans_up_tasks(mock_websocket) -> None:
    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._state = ConnectionState.CONNECTED
    connection._running = True
    connection._receive_task = asyncio.create_task(asyncio.sleep(0.01))
    connection._reconnect_task = asyncio.create_task(asyncio.sleep(0.01))

    await connection.disconnect()

    assert connection.state == ConnectionState.DISCONNECTED
    mock_websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_no_tasks() -> None:
    connection = ServerConnection()
    connection._ws = None

    await connection.disconnect()

    assert connection.state == ConnectionState.DISCONNECTED


@pytest.mark.asyncio
async def test_receive_loop_connection_closed(monkeypatch, mock_websocket) -> None:
    class FakeClosed(Exception):
        pass

    monkeypatch.setattr(websockets, "ConnectionClosed", FakeClosed)
    mock_websocket.recv = AsyncMock(side_effect=FakeClosed())

    async def reconnect_stub():
        return None

    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._running = True
    monkeypatch.setattr(connection, "_reconnect", reconnect_stub)

    await connection._receive_loop()

    assert connection.state == ConnectionState.DISCONNECTED
    assert connection.state == ConnectionState.DISCONNECTED


@pytest.mark.asyncio
async def test_receive_loop_connection_closed_not_running(monkeypatch, mock_websocket) -> None:
    class FakeClosed(Exception):
        pass

    monkeypatch.setattr(websockets, "ConnectionClosed", FakeClosed)
    async def recv_stub():
        connection._running = False
        raise FakeClosed()

    mock_websocket.recv = AsyncMock(side_effect=recv_stub)

    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._running = True
    connection._reconnect = AsyncMock()

    await connection._receive_loop()

    connection._reconnect.assert_not_called()


@pytest.mark.asyncio
async def test_receive_loop_generic_error(mock_websocket) -> None:
    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._running = True

    async def recv_stub():
        connection._running = False
        raise RuntimeError("boom")

    mock_websocket.recv = AsyncMock(side_effect=recv_stub)

    await connection._receive_loop()


@pytest.mark.asyncio
async def test_receive_loop_message(monkeypatch, mock_websocket) -> None:
    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._running = True

    async def recv_stub():
        return json.dumps({"type": "PONG"})

    async def handle_stub(_message):
        connection._running = False

    mock_websocket.recv = AsyncMock(side_effect=recv_stub)
    monkeypatch.setattr(connection, "_handle_message", AsyncMock(side_effect=handle_stub))

    await connection._receive_loop()


@pytest.mark.asyncio
async def test_handle_message_transcription(monkeypatch) -> None:
    response = {}

    def on_transcription(result):
        response["text"] = result.text
        response["processing"] = result.processing

    connection = ServerConnection(on_transcription=on_transcription)
    message = json.dumps({"type": "TRANSCRIPTION", "text": "hi", "processing": True})

    await connection._handle_message(message)

    assert response == {"text": "hi", "processing": True}


@pytest.mark.asyncio
async def test_handle_message_transcription_no_callback() -> None:
    connection = ServerConnection()
    message = json.dumps({"type": "TRANSCRIPTION", "text": "hi", "processing": False})

    await connection._handle_message(message)


@pytest.mark.asyncio
async def test_handle_message_processing() -> None:
    connection = ServerConnection()
    await connection._handle_message(json.dumps({"type": "PROCESSING"}))


@pytest.mark.asyncio
async def test_handle_message_error() -> None:
    connection = ServerConnection()
    await connection._handle_message(json.dumps({"type": "ERROR", "error": "bad"}))


@pytest.mark.asyncio
async def test_handle_message_pong() -> None:
    connection = ServerConnection()
    await connection._handle_message(json.dumps({"type": "PONG"}))


@pytest.mark.asyncio
async def test_handle_message_unknown_type() -> None:
    connection = ServerConnection()
    await connection._handle_message(json.dumps({"type": "UNKNOWN"}))


@pytest.mark.asyncio
async def test_handle_message_invalid_json() -> None:
    connection = ServerConnection()
    await connection._handle_message("{bad json")


@pytest.mark.asyncio
async def test_handle_message_bytes() -> None:
    connection = ServerConnection()
    await connection._handle_message(b"{\"type\": \"PONG\"}")


@pytest.mark.asyncio
async def test_handle_message_callback_error() -> None:
    def on_transcription(_result):
        raise RuntimeError("boom")

    connection = ServerConnection(on_transcription=on_transcription)
    message = json.dumps({"type": "TRANSCRIPTION", "text": "hi", "processing": False})

    await connection._handle_message(message)


@pytest.mark.asyncio
async def test_send_audio_not_connected() -> None:
    connection = ServerConnection()
    await connection.send_audio(b"abc")


@pytest.mark.asyncio
async def test_send_audio_success(mock_websocket) -> None:
    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._state = ConnectionState.CONNECTED

    await connection.send_audio(b"a" * (64 * 1024 + 10), sample_rate=22050, channels=2)

    assert mock_websocket.send.await_count == 4
    start_message = json.loads(mock_websocket.send.await_args_list[0].args[0])
    end_message = json.loads(mock_websocket.send.await_args_list[-1].args[0])

    assert start_message["type"] == "AUDIO_START"
    assert start_message["sample_rate"] == 22050
    assert start_message["channels"] == 2
    assert end_message["type"] == "AUDIO_END"


@pytest.mark.asyncio
async def test_send_audio_error(mock_websocket) -> None:
    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._state = ConnectionState.CONNECTED
    mock_websocket.send = AsyncMock(side_effect=RuntimeError("boom"))

    await connection.send_audio(b"abc")


@pytest.mark.asyncio
async def test_ping_not_connected() -> None:
    connection = ServerConnection()
    assert await connection.ping() is False


@pytest.mark.asyncio
async def test_ping_connected(mock_websocket) -> None:
    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._state = ConnectionState.CONNECTED

    assert await connection.ping() is True


@pytest.mark.asyncio
async def test_ping_error(mock_websocket) -> None:
    connection = ServerConnection()
    connection._ws = mock_websocket
    connection._state = ConnectionState.CONNECTED
    mock_websocket.send = AsyncMock(side_effect=RuntimeError("boom"))

    assert await connection.ping() is False


@pytest.mark.asyncio
async def test_start_uses_receive_loop(monkeypatch) -> None:
    connection = ServerConnection()

    async def connect_stub():
        connection._state = ConnectionState.CONNECTED
        return True

    monkeypatch.setattr(connection, "connect", connect_stub)
    monkeypatch.setattr(connection, "_receive_loop", AsyncMock())

    await connection.start()

    assert connection._receive_task is not None
    await connection._receive_task


@pytest.mark.asyncio
async def test_start_uses_reconnect(monkeypatch) -> None:
    connection = ServerConnection()

    async def connect_stub():
        return False

    monkeypatch.setattr(connection, "connect", connect_stub)
    monkeypatch.setattr(connection, "_reconnect", AsyncMock())

    await connection.start()

    assert connection._reconnect_task is not None
    await connection._reconnect_task


@pytest.mark.asyncio
async def test_reconnect_retries(monkeypatch) -> None:
    connection = ServerConnection()
    connection._running = True
    connection._state = ConnectionState.DISCONNECTED

    connect_calls = []

    async def connect_stub():
        connect_calls.append(True)
        return len(connect_calls) > 1

    async def sleep_stub(_delay):
        return None

    monkeypatch.setattr(connection, "connect", connect_stub)
    monkeypatch.setattr(asyncio, "sleep", sleep_stub)
    monkeypatch.setattr(connection, "_receive_loop", AsyncMock())

    await connection._reconnect(delay=0.01)

    assert len(connect_calls) == 2
    assert connection._receive_task is not None
    await connection._receive_task


@pytest.mark.asyncio
async def test_reconnect_noop() -> None:
    connection = ServerConnection()
    connection._running = False

    await connection._reconnect()
