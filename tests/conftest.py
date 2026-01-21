"""Shared test fixtures."""

# Prevent PortAudio from initializing during tests.
# Importing sounddevice can spawn PortAudio threads that segfault under pytest teardown
# when combined with asyncio/mocking in this suite, so we replace it with a stub module
# before any vox.client.audio imports occur.
import sys
import types

if "sounddevice" not in sys.modules:
    stub = types.SimpleNamespace()

    class _StubInputStream:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def close(self) -> None:
            pass

    stub.InputStream = _StubInputStream
    stub.CallbackFlags = object
    stub.default = types.SimpleNamespace(device=(None, None))
    stub.query_devices = lambda *_args, **_kwargs: []
    sys.modules["sounddevice"] = stub

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from vox.config import Config
from vox.config.schema import (
    AgentConfig,
    HotkeyConfig,
    LLMConfig,
    ModelConfig,
    OutputConfig,
    OverlayConfig,
    ServerConfig,
)


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
        yield config_dir


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
        yield cache_dir


@pytest.fixture
def sample_config() -> Config:
    """Provide a sample Config object for testing."""
    return Config(
        hotkey=HotkeyConfig(trigger="ctrl+space"),
        server=ServerConfig(host="localhost", port=9876),
        model=ModelConfig(default="small.en", device="cpu", compute_type="int8"),
        output=OutputConfig(method="both", typing_method="paste"),
        overlay=OverlayConfig(enabled=True, position="top-right"),
        agent=AgentConfig(
            enabled=True,
            keyword="Agent",
            llm=LLMConfig(
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                api_key="${ANTHROPIC_API_KEY}",
            ),
        ),
    )


@pytest.fixture
def mock_dbus_bus() -> Generator[MagicMock, None, None]:
    """Mock D-Bus MessageBus."""
    with patch("vox.client.hotkey.MessageBus") as mock_bus_class:
        mock_bus = AsyncMock()
        mock_bus_class.return_value.connect = AsyncMock(return_value=mock_bus)

        mock_introspection = MagicMock()
        mock_bus.introspect = AsyncMock(return_value=mock_introspection)

        mock_proxy = MagicMock()
        mock_bus.get_proxy_object = MagicMock(return_value=mock_proxy)

        mock_interface = MagicMock()
        mock_interface.call_get_state = AsyncMock(return_value="idle")
        mock_interface.call_set_state = AsyncMock()
        mock_interface.on_hotkey_pressed = MagicMock()
        mock_interface.on_hotkey_released = MagicMock()
        mock_proxy.get_interface = MagicMock(return_value=mock_interface)

        mock_bus.disconnect = MagicMock()

        yield mock_bus


@pytest.fixture
def mock_sounddevice() -> Generator[MagicMock, None, None]:
    """Mock sounddevice module."""
    with patch("vox.client.audio.sd") as mock_sd:
        mock_sd.default.device = (0, 0)
        mock_sd.query_devices.return_value = [
            {
                "name": "Test Microphone",
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "Test Speaker",
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000.0,
            },
        ]

        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        yield mock_sd


@pytest.fixture
def mock_websocket() -> Generator[AsyncMock, None, None]:
    """Mock WebSocket connection."""
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock()
    mock_ws.close = AsyncMock()
    mock_ws.remote_address = ("127.0.0.1", 12345)

    yield mock_ws


@pytest.fixture
def sample_audio_bytes() -> bytes:
    """Provide sample audio bytes for testing."""
    # Generate 1 second of silence at 16kHz, 16-bit mono
    duration = 1.0
    sample_rate = 16000
    samples = int(duration * sample_rate)

    # Create a simple sine wave at 440 Hz for more realistic audio
    t = np.linspace(0, duration, samples, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)

    return audio.tobytes()


@pytest.fixture
def mock_whisper_model() -> Generator[MagicMock, None, None]:
    """Mock WhisperModel."""
    with patch("vox.server.transcriber.WhisperModel") as mock_model_class:
        mock_model = MagicMock()

        # Create mock segments
        mock_segment = MagicMock()
        mock_segment.text = "Hello, world!"

        # Create mock info
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 1.5

        mock_model.transcribe.return_value = (iter([mock_segment]), mock_info)
        mock_model_class.return_value = mock_model

        yield mock_model


@pytest.fixture
def mock_litellm() -> Generator[MagicMock, None, None]:
    """Mock litellm module."""
    with patch("vox.server.agent.litellm") as mock_litellm:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Transformed text"

        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        yield mock_litellm


@pytest.fixture
def mock_huggingface_hub() -> Generator[MagicMock, None, None]:
    """Mock huggingface_hub module."""
    with patch("vox.server.model_manager.snapshot_download") as mock_download:
        mock_download.return_value = "/tmp/model"
        yield mock_download


@pytest.fixture
def models_yaml_content() -> str:
    """Provide sample models.yaml content."""
    return """models:
  - id: tiny.en
    name: Tiny (English)
    size: 75MB
    repo: Systran/faster-whisper-tiny.en

  - id: small.en
    name: Small (English)
    size: 488MB
    repo: Systran/faster-whisper-small.en
"""


@pytest.fixture
def mock_subprocess() -> Generator[MagicMock, None, None]:
    """Mock asyncio.create_subprocess_exec for output tests."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        yield mock_exec
