"""Tests for vox.client.output."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vox.client import output as output_module
from vox.client.output import OutputHandler


class _FakeStdin:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, chunk: bytes) -> None:
        self.data += chunk

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stderr = SimpleNamespace(read=AsyncMock(return_value=stderr))
        self.stdin = _FakeStdin()

    async def wait(self) -> None:
        return None

    async def communicate(self):
        return (b"", b"")


@pytest.mark.asyncio
async def test_output_empty_text() -> None:
    handler = OutputHandler()
    await handler.output("")


@pytest.mark.asyncio
async def test_output_clipboard_only(monkeypatch) -> None:
    handler = OutputHandler(method="clipboard")

    copy_called = False

    async def copy_stub(_text):
        nonlocal copy_called
        copy_called = True

    monkeypatch.setattr(handler, "_copy_to_clipboard", copy_stub)

    await handler.output("hi")

    assert copy_called is True


@pytest.mark.asyncio
async def test_output_type_paste(monkeypatch) -> None:
    handler = OutputHandler(method="type", typing_method="paste")
    paste_called = False
    copy_called = False

    async def copy_stub(_text: str) -> None:
        nonlocal copy_called
        copy_called = True

    async def paste_stub():
        nonlocal paste_called
        paste_called = True

    monkeypatch.setattr(handler, "_copy_to_clipboard", copy_stub)
    monkeypatch.setattr(handler, "_paste", paste_stub)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await handler.output("hi")

    assert paste_called is True
    assert copy_called is True


@pytest.mark.asyncio
async def test_output_type_paste_copies_clipboard(monkeypatch) -> None:
    handler = OutputHandler(method="type", typing_method="paste")
    calls = []

    async def copy_stub(_text: str) -> None:
        calls.append("copy")

    async def paste_stub() -> None:
        calls.append("paste")

    monkeypatch.setattr(handler, "_copy_to_clipboard", copy_stub)
    monkeypatch.setattr(handler, "_paste", paste_stub)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await handler.output("hello")

    assert calls == ["copy", "paste"]


@pytest.mark.asyncio
async def test_output_both_paste_copies_once(monkeypatch) -> None:
    handler = OutputHandler(method="both", typing_method="paste")
    calls = []

    async def copy_stub(_text: str) -> None:
        calls.append("copy")

    async def paste_stub() -> None:
        calls.append("paste")

    monkeypatch.setattr(handler, "_copy_to_clipboard", copy_stub)
    monkeypatch.setattr(handler, "_paste", paste_stub)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await handler.output("hello")

    assert calls == ["copy", "paste"]


@pytest.mark.asyncio
async def test_output_type_direct(monkeypatch) -> None:
    handler = OutputHandler(method="type", typing_method="type")
    type_called = False

    async def type_stub(_text):
        nonlocal type_called
        type_called = True

    monkeypatch.setattr(handler, "_type_text", type_stub)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await handler.output("hi")

    assert type_called is True


@pytest.mark.asyncio
async def test_copy_to_clipboard_success(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=0)

    async def create_proc(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._copy_to_clipboard("text")

    assert process.stdin.data == b"text"
    assert process.stdin.closed is True


@pytest.mark.asyncio
async def test_copy_to_clipboard_error(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=1, stderr=b"bad")

    async def create_proc(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._copy_to_clipboard("text")


@pytest.mark.asyncio
async def test_copy_to_clipboard_timeout(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=0)

    async def create_proc(*_args, **_kwargs):
        return process

    async def wait_for_stub(*_args, **_kwargs):
        _args[0].close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)
    monkeypatch.setattr(asyncio, "wait_for", wait_for_stub)

    await handler._copy_to_clipboard("text")


@pytest.mark.asyncio
async def test_paste_success(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=0)

    async def create_proc(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._paste()


@pytest.mark.asyncio
async def test_paste_ydotoold_error(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=1, stderr=b"ydotoold socket")

    async def create_proc(*_args, **_kwargs):
        return process

    process.communicate = AsyncMock(return_value=(b"", process.stderr.read.return_value))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._paste()


@pytest.mark.asyncio
async def test_paste_other_error(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=1, stderr=b"other")

    async def create_proc(*_args, **_kwargs):
        return process

    process.communicate = AsyncMock(return_value=(b"", process.stderr.read.return_value))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._paste()


@pytest.mark.asyncio
async def test_paste_file_not_found(monkeypatch) -> None:
    handler = OutputHandler()

    async def create_proc(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._paste()


@pytest.mark.asyncio
async def test_paste_exception(monkeypatch) -> None:
    handler = OutputHandler()

    async def create_proc(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._paste()


@pytest.mark.asyncio
async def test_type_text_success(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=0)

    async def create_proc(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._type_text("hello")


@pytest.mark.asyncio
async def test_type_text_preserves_leading_chars(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=0)
    captured_args = None

    async def create_proc(*args, **_kwargs):
        nonlocal captured_args
        captured_args = args
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    text = "  --leading"
    await handler._type_text(text)

    assert captured_args == ("ydotool", "type", "--", text)


@pytest.mark.asyncio
async def test_type_text_ydotoold_error(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=1, stderr=b"ydotoold socket")

    async def create_proc(*_args, **_kwargs):
        return process

    process.communicate = AsyncMock(return_value=(b"", process.stderr.read.return_value))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._type_text("hello")


@pytest.mark.asyncio
async def test_type_text_other_error(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=1, stderr=b"other")

    async def create_proc(*_args, **_kwargs):
        return process

    process.communicate = AsyncMock(return_value=(b"", process.stderr.read.return_value))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._type_text("hello")


@pytest.mark.asyncio
async def test_type_text_file_not_found(monkeypatch) -> None:
    handler = OutputHandler()

    async def create_proc(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._type_text("hello")


@pytest.mark.asyncio
async def test_type_text_exception(monkeypatch) -> None:
    handler = OutputHandler()

    async def create_proc(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    await handler._type_text("hello")


def test_check_wayland_tools(monkeypatch) -> None:
    def run_stub(*_args, **_kwargs):
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(output_module.subprocess, "run", run_stub)

    tools = output_module.check_wayland_tools()

    assert tools["wl-copy"] is True


def test_check_wayland_tools_nonzero(monkeypatch) -> None:
    def run_stub(*_args, **_kwargs):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(output_module.subprocess, "run", run_stub)

    tools = output_module.check_wayland_tools()

    assert tools["wl-copy"] is False


def test_check_wayland_tools_exception(monkeypatch) -> None:
    def run_stub(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(output_module.subprocess, "run", run_stub)

    tools = output_module.check_wayland_tools()

    assert tools["wl-copy"] is False


def test_check_ydotool_daemon_access(monkeypatch) -> None:
    monkeypatch.setattr("os.access", lambda *_args, **_kwargs: True)

    assert output_module.check_ydotool_daemon() is True


def test_check_ydotool_daemon_runtime_socket(monkeypatch) -> None:
    monkeypatch.setattr("os.access", lambda *_args, **_kwargs: False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/runtime")

    def exists_stub(path):
        return path == "/tmp/runtime/.ydotool_socket"

    monkeypatch.setattr("os.path.exists", exists_stub)

    assert output_module.check_ydotool_daemon() is True


def test_check_ydotool_daemon_tmp_socket(monkeypatch) -> None:
    monkeypatch.setattr("os.access", lambda *_args, **_kwargs: False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("os.path.exists", lambda path: path == "/tmp/.ydotool_socket")

    assert output_module.check_ydotool_daemon() is True


def test_check_ydotool_daemon_runtime_missing_tmp_socket(monkeypatch) -> None:
    monkeypatch.setattr("os.access", lambda *_args, **_kwargs: False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/runtime")
    monkeypatch.setattr("os.path.exists", lambda path: path == "/tmp/.ydotool_socket")

    assert output_module.check_ydotool_daemon() is True


def test_check_ydotool_daemon_false(monkeypatch) -> None:
    monkeypatch.setattr("os.access", lambda *_args, **_kwargs: False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("os.path.exists", lambda *_args: False)

    assert output_module.check_ydotool_daemon() is False
