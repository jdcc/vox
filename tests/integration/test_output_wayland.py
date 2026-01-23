"""Integration tests for Wayland output handling."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess

import pytest
import pytest_asyncio

from vox.client.output import OutputHandler
from vox.client.portal_input import PortalInput, PortalInputError

pytestmark = pytest.mark.asyncio(scope="session")


@pytest_asyncio.fixture(scope="session")
async def portal_input() -> PortalInput:
    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        pytest.skip("Wayland session required")
    if not os.environ.get("WAYLAND_DISPLAY"):
        pytest.skip("WAYLAND_DISPLAY not set")

    required_tools = ["wl-copy", "wl-paste", "zenity"]
    missing = [tool for tool in required_tools if not shutil.which(tool)]
    if missing:
        pytest.skip(f"Missing tools: {', '.join(missing)}")

    portal = PortalInput()
    try:
        print("Waiting for portal approval to start RemoteDesktop session...")
        await asyncio.wait_for(portal.start(), timeout=60)
    except PortalInputError as exc:
        pytest.skip(f"Portal input not available: {exc}")
    except asyncio.TimeoutError:
        pytest.skip("Portal permission prompt timed out after 60s")

    yield portal

    await portal.stop()


def _start_zenity() -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["zenity", "--entry", "--title", "vox-it", "--text", "vox it test"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


async def _wait_for_window() -> None:
    await asyncio.sleep(0.7)


async def _send_enter(portal: PortalInput) -> None:
    await asyncio.sleep(0.1)
    await portal.send_key_press(28)


@pytest.mark.integration
@pytest.mark.parametrize("text", ["hello", "  --leading", "*#[]{}"])
async def test_output_paste_integration(text: str, portal_input: PortalInput) -> None:
    process = _start_zenity()

    try:
        await _wait_for_window()
        handler = OutputHandler(method="type", typing_method="paste")
        handler._portal_input = portal_input
        await handler.output(text)
        await asyncio.sleep(0.3)
        await _send_enter(portal_input)
        stdout, _stderr = process.communicate(timeout=5)
        assert stdout.rstrip("\n") == text
    finally:
        if process.poll() is None:
            process.kill()


@pytest.mark.integration
@pytest.mark.parametrize("text", ["hello", "  --leading", "*#[]{}"])
async def test_output_type_integration(text: str, portal_input: PortalInput) -> None:
    process = _start_zenity()

    try:
        await _wait_for_window()
        handler = OutputHandler(method="type", typing_method="type")
        handler._portal_input = portal_input
        await handler.output(text)
        await _send_enter(portal_input)
        stdout, _stderr = process.communicate(timeout=5)
        assert stdout.rstrip("\n") == text
    finally:
        if process.poll() is None:
            process.kill()


@pytest.mark.integration
async def test_output_both_paste_preserves_clipboard(portal_input: PortalInput) -> None:
    text = "clipboard-check"
    process = _start_zenity()

    try:
        await _wait_for_window()
        handler = OutputHandler(method="both", typing_method="paste")
        handler._portal_input = portal_input
        await handler.output(text)

        clipboard = subprocess.run(
            ["wl-paste", "--no-newline"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert clipboard.stdout == text

        await _send_enter(portal_input)
        stdout, _stderr = process.communicate(timeout=5)
        assert stdout.rstrip("\n") == text
    finally:
        if process.poll() is None:
            process.kill()
