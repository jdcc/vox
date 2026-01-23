"""Tests for vox.client.output."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vox.client import output as output_module
from vox.client.output import OutputHandler


class _FakeStdin:
    def __init__(self):
        self.data = ""
        self.closed = False

    def write(self, chunk: str) -> None:
        self.data += chunk

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = SimpleNamespace(read=lambda: stderr)
        self.stdin = _FakeStdin()
        self.raise_timeout = False

    def wait(self, timeout: float | None = None) -> None:
        if self.raise_timeout:
            raise output_module.subprocess.TimeoutExpired(cmd="wl-copy", timeout=timeout)
        return None


class _FakePopen:
    def __init__(self, stdin: _FakeStdin | None, returncode: int = 0, stderr: str = "") -> None:
        self.stdin = stdin
        self.returncode = returncode
        self.stderr = SimpleNamespace(read=lambda: stderr)
        self.raise_timeout = False

    def wait(self, timeout: float | None = None) -> None:
        if self.raise_timeout:
            raise output_module.subprocess.TimeoutExpired(cmd="wl-copy", timeout=timeout)
        return None


class _FakePortalInput:
    def __init__(self):
        self.active = True
        self.paste_called = False
        self.type_called = False
        self.started = False
        self.stopped = False
        self.raise_on_paste = False
        self.raise_on_type = False

    async def send_paste(self) -> None:
        if self.raise_on_paste:
            raise RuntimeError("paste failed")
        self.paste_called = True

    async def type_text(self, _text: str) -> None:
        if self.raise_on_type:
            raise RuntimeError("type failed")
        self.type_called = True

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


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
    monkeypatch.setattr(handler, "_wait_for_clipboard", AsyncMock(return_value=True))
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
    monkeypatch.setattr(handler, "_wait_for_clipboard", AsyncMock(return_value=True))
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
    monkeypatch.setattr(handler, "_wait_for_clipboard", AsyncMock(return_value=True))
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
async def test_start_portal_not_needed(monkeypatch) -> None:
    handler = OutputHandler(method="clipboard")
    await handler.start()

    assert handler._portal_input is None


@pytest.mark.asyncio
async def test_start_portal_wayland(monkeypatch) -> None:
    handler = OutputHandler(method="type")
    portal = _FakePortalInput()

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(output_module, "PortalInput", lambda: portal)

    await handler.start()

    assert handler._portal_input is portal
    assert portal.started is True


@pytest.mark.asyncio
async def test_start_portal_non_wayland(monkeypatch) -> None:
    handler = OutputHandler(method="type")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    await handler.start()

    assert handler._portal_input is None


@pytest.mark.asyncio
async def test_start_portal_active(monkeypatch) -> None:
    handler = OutputHandler(method="type")
    portal = _FakePortalInput()
    handler._portal_input = portal

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")

    await handler.start()

    assert portal.started is False


@pytest.mark.asyncio
async def test_start_portal_failure(monkeypatch, caplog) -> None:
    handler = OutputHandler(method="type")

    class _FailPortal:
        active = False

        async def start(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(output_module, "PortalInput", lambda: _FailPortal())

    await handler.start()

    assert handler._portal_input is None
    assert "Portal input unavailable" in caplog.text


@pytest.mark.asyncio
async def test_stop_portal(monkeypatch) -> None:
    handler = OutputHandler(method="type")
    portal = _FakePortalInput()
    handler._portal_input = portal

    await handler.stop()

    assert portal.stopped is True


@pytest.mark.asyncio
async def test_copy_to_clipboard_success(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=0)

    def popen_stub(*_args, **_kwargs):
        return process

    monkeypatch.setattr(output_module.subprocess, "Popen", popen_stub)

    await handler._copy_to_clipboard("text")

    assert process.stdin.data == "text"
    assert process.stdin.closed is True


@pytest.mark.asyncio
async def test_copy_to_clipboard_error(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=1, stderr="bad")

    def popen_stub(*_args, **_kwargs):
        return process

    monkeypatch.setattr(output_module.subprocess, "Popen", popen_stub)

    await handler._copy_to_clipboard("text")


@pytest.mark.asyncio
async def test_copy_to_clipboard_timeout(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakeProcess(returncode=0)
    process.raise_timeout = True

    def popen_stub(*_args, **_kwargs):
        return process

    monkeypatch.setattr(output_module.subprocess, "Popen", popen_stub)

    await handler._copy_to_clipboard("text")


@pytest.mark.asyncio
async def test_paste_without_portal() -> None:
    handler = OutputHandler()
    await handler._paste()


@pytest.mark.asyncio
async def test_paste_portal() -> None:
    handler = OutputHandler()
    portal = _FakePortalInput()
    handler._portal_input = portal

    await handler._paste()

    assert portal.paste_called is True


@pytest.mark.asyncio
async def test_paste_portal_error() -> None:
    handler = OutputHandler()
    portal = _FakePortalInput()
    portal.raise_on_paste = True
    handler._portal_input = portal

    await handler._paste()


@pytest.mark.asyncio
async def test_type_text_without_portal() -> None:
    handler = OutputHandler()
    await handler._type_text("hello")


@pytest.mark.asyncio
async def test_type_text_portal() -> None:
    handler = OutputHandler()
    portal = _FakePortalInput()
    handler._portal_input = portal

    await handler._type_text("hello")

    assert portal.type_called is True


@pytest.mark.asyncio
async def test_type_text_portal_error() -> None:
    handler = OutputHandler()
    portal = _FakePortalInput()
    portal.raise_on_type = True
    handler._portal_input = portal

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


@pytest.mark.asyncio
async def test_output_type_paste_recopies_on_mismatch(monkeypatch) -> None:
    handler = OutputHandler(method="type", typing_method="paste")
    calls = []

    async def copy_stub(_text: str) -> None:
        calls.append("copy")

    async def paste_stub() -> None:
        calls.append("paste")

    monkeypatch.setattr(handler, "_copy_to_clipboard", copy_stub)
    monkeypatch.setattr(handler, "_paste", paste_stub)
    monkeypatch.setattr(handler, "_wait_for_clipboard", AsyncMock(side_effect=[False, True]))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await handler.output("hello")

    assert calls == ["copy", "copy", "paste"]


def test_copy_to_clipboard_sync_no_stdin(monkeypatch) -> None:
    handler = OutputHandler()
    process = _FakePopen(stdin=None)

    def popen_stub(*_args, **_kwargs):
        return process

    monkeypatch.setattr(output_module.subprocess, "Popen", popen_stub)

    handler._copy_to_clipboard_sync("text")


def test_copy_to_clipboard_sync_write_error(monkeypatch) -> None:
    handler = OutputHandler()
    stdin = _FakeStdin()

    def write_raises(_text: str) -> None:
        raise OSError("write fail")

    stdin.write = write_raises
    process = _FakePopen(stdin=stdin)

    def popen_stub(*_args, **_kwargs):
        return process

    monkeypatch.setattr(output_module.subprocess, "Popen", popen_stub)

    handler._copy_to_clipboard_sync("text")


@pytest.mark.asyncio
async def test_wait_for_clipboard_missing_tool(monkeypatch) -> None:
    handler = OutputHandler()

    monkeypatch.setattr(output_module.shutil, "which", lambda _name: None)

    assert await handler._wait_for_clipboard("text") is True


@pytest.mark.asyncio
async def test_wait_for_clipboard_match(monkeypatch) -> None:
    handler = OutputHandler()

    class _PasteProcess:
        async def communicate(self):
            return (b"hello", b"")

    async def create_proc(*_args, **_kwargs):
        return _PasteProcess()

    monkeypatch.setattr(output_module.shutil, "which", lambda _name: "/usr/bin/wl-paste")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    assert await handler._wait_for_clipboard("hello") is True


@pytest.mark.asyncio
async def test_wait_for_clipboard_timeout(monkeypatch) -> None:
    handler = OutputHandler()

    class _PasteProcess:
        async def communicate(self):
            return (b"nope", b"")

    async def create_proc(*_args, **_kwargs):
        return _PasteProcess()

    class _FakeLoop:
        def __init__(self):
            self._times = iter([0.0, 0.2])

        def time(self) -> float:
            return next(self._times)

    loop = _FakeLoop()
    monkeypatch.setattr(output_module.shutil, "which", lambda _name: "/usr/bin/wl-paste")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    assert await handler._wait_for_clipboard("hello", timeout=0.1) is False


@pytest.mark.asyncio
async def test_wait_for_clipboard_missing_paste(monkeypatch) -> None:
    handler = OutputHandler()

    async def create_proc(*_args, **_kwargs):
        raise FileNotFoundError

    class _FakeLoop:
        def __init__(self):
            self._times = iter([0.0, 0.2])

        def time(self) -> float:
            return next(self._times)

    loop = _FakeLoop()
    monkeypatch.setattr(output_module.shutil, "which", lambda _name: "/usr/bin/wl-paste")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    assert await handler._wait_for_clipboard("hello", timeout=0.1) is False
