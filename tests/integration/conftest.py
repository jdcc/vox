"""Integration test asyncio configuration."""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """Provide a session-scoped event loop for integration tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def pytest_configure(config) -> None:
    """Ensure pytest-asyncio uses a session-scoped loop for integration tests."""
    config._inicache["asyncio_default_fixture_loop_scope"] = "session"
