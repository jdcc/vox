"""Tests for vox.config.schema module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from vox.config.schema import (
    AgentConfig,
    AudioConfig,
    Config,
    HotkeyConfig,
    LLMConfig,
    ModelConfig,
    OutputConfig,
    OverlayConfig,
    ServerConfig,
    create_default_config,
    get_cache_dir,
    get_config_dir,
    get_config_path,
    load_config,
    save_config,
)


class TestHotkeyConfig:
    """Tests for HotkeyConfig model."""

    def test_default_values(self):
        config = HotkeyConfig()
        assert config.trigger == "ctrl+space"

    def test_custom_trigger(self):
        config = HotkeyConfig(trigger="alt+r")
        assert config.trigger == "alt+r"


class TestServerConfig:
    """Tests for ServerConfig model."""

    def test_default_values(self):
        config = ServerConfig()
        assert config.host == "localhost"
        assert config.port == 9876

    def test_custom_values(self):
        config = ServerConfig(host="192.168.1.1", port=8080)
        assert config.host == "192.168.1.1"
        assert config.port == 8080


class TestModelConfig:
    """Tests for ModelConfig model."""

    def test_default_values(self):
        config = ModelConfig()
        assert config.default == "small.en"
        assert config.device == "auto"
        assert config.compute_type == "int8"

    def test_valid_device_values(self):
        for device in ["auto", "cpu", "cuda"]:
            config = ModelConfig(device=device)
            assert config.device == device

    def test_invalid_device_value(self):
        with pytest.raises(ValueError):
            ModelConfig(device="invalid")


class TestOutputConfig:
    """Tests for OutputConfig model."""

    def test_default_values(self):
        config = OutputConfig()
        assert config.method == "both"
        assert config.typing_method == "paste"

    def test_valid_method_values(self):
        for method in ["clipboard", "type", "both"]:
            config = OutputConfig(method=method)
            assert config.method == method

    def test_valid_typing_method_values(self):
        for typing_method in ["paste", "type"]:
            config = OutputConfig(typing_method=typing_method)
            assert config.typing_method == typing_method

    def test_invalid_method_value(self):
        with pytest.raises(ValueError):
            OutputConfig(method="invalid")


class TestAudioConfig:
    """Tests for AudioConfig model."""

    def test_default_values(self):
        config = AudioConfig()
        assert config.input_device is None

    def test_custom_input_device(self):
        config = AudioConfig(input_device="USB Mic")
        assert config.input_device == "USB Mic"


class TestOverlayConfig:
    """Tests for OverlayConfig model."""

    def test_default_values(self):
        config = OverlayConfig()
        assert config.enabled is True
        assert config.position == "top-right"

    def test_valid_position_values(self):
        for position in ["top-right", "top-center", "bottom-right"]:
            config = OverlayConfig(position=position)
            assert config.position == position

    def test_disabled_overlay(self):
        config = OverlayConfig(enabled=False)
        assert config.enabled is False


class TestLLMConfig:
    """Tests for LLMConfig model."""

    def test_default_values(self):
        config = LLMConfig()
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.api_key == ""
        assert config.api_base == ""

    def test_get_api_key_direct(self):
        config = LLMConfig(api_key="sk-12345")
        assert config.get_api_key() == "sk-12345"

    def test_get_api_key_env_var(self):
        config = LLMConfig(api_key="${TEST_API_KEY}")
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-from-env"}):
            assert config.get_api_key() == "sk-from-env"

    def test_get_api_key_env_var_not_set(self):
        config = LLMConfig(api_key="${NONEXISTENT_KEY}")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NONEXISTENT_KEY", None)
            assert config.get_api_key() == ""

    def test_get_api_key_partial_env_var_syntax(self):
        # Not proper env var syntax, should return as-is
        config = LLMConfig(api_key="${INCOMPLETE")
        assert config.get_api_key() == "${INCOMPLETE"

        config = LLMConfig(api_key="INCOMPLETE}")
        assert config.get_api_key() == "INCOMPLETE}"


class TestAgentConfig:
    """Tests for AgentConfig model."""

    def test_default_values(self):
        config = AgentConfig()
        assert config.enabled is True
        assert config.keyword == "Agent"
        assert config.user_name == ""
        assert isinstance(config.llm, LLMConfig)

    def test_custom_values(self):
        config = AgentConfig(
            enabled=False,
            keyword="Hey Claude",
            llm=LLMConfig(provider="openai", model="gpt-4"),
        )
        assert config.enabled is False
        assert config.keyword == "Hey Claude"
        assert config.llm.provider == "openai"


class TestConfig:
    """Tests for main Config model."""

    def test_default_values(self):
        config = Config()
        assert isinstance(config.hotkey, HotkeyConfig)
        assert isinstance(config.server, ServerConfig)
        assert isinstance(config.model, ModelConfig)
        assert isinstance(config.audio, AudioConfig)
        assert isinstance(config.output, OutputConfig)
        assert isinstance(config.overlay, OverlayConfig)
        assert isinstance(config.agent, AgentConfig)

    def test_custom_values(self):
        config = Config(
            hotkey=HotkeyConfig(trigger="f1"),
            server=ServerConfig(port=1234),
        )
        assert config.hotkey.trigger == "f1"
        assert config.server.port == 1234

    def test_model_dump(self):
        config = Config()
        data = config.model_dump()
        assert "hotkey" in data
        assert "server" in data
        assert "model" in data
        assert "audio" in data
        assert data["hotkey"]["trigger"] == "ctrl+space"


class TestConfigPaths:
    """Tests for config path functions."""

    def test_get_config_dir_default(self, tmp_path):
        with patch.dict(os.environ, {"HOME": str(tmp_path)}, clear=False):
            os.environ.pop("XDG_CONFIG_HOME", None)
            config_dir = get_config_dir()
            assert config_dir == Path.home() / ".config" / "vox"

    def test_get_config_dir_xdg(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config_dir = get_config_dir()
            assert config_dir == tmp_path / "vox"

    def test_get_cache_dir_default(self, tmp_path):
        with patch.dict(os.environ, {"HOME": str(tmp_path)}, clear=False):
            os.environ.pop("XDG_CACHE_HOME", None)
            cache_dir = get_cache_dir()
            assert cache_dir == Path.home() / ".cache" / "vox"

    def test_get_cache_dir_xdg(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
            cache_dir = get_cache_dir()
            assert cache_dir == tmp_path / "vox"

    def test_get_config_path(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config_path = get_config_path()
            assert config_path == tmp_path / "vox" / "config.yaml"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_no_file(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config = load_config()
            assert isinstance(config, Config)
            # Should have default values
            assert config.hotkey.trigger == "ctrl+space"

    def test_load_config_existing_file(self, tmp_path):
        config_dir = tmp_path / "vox"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"

        config_data = {
            "hotkey": {"trigger": "alt+r"},
            "server": {"port": 1234},
        }
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config = load_config()
            assert config.hotkey.trigger == "alt+r"
            assert config.server.port == 1234

    def test_load_config_empty_file(self, tmp_path):
        config_dir = tmp_path / "vox"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text("")

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config = load_config()
            assert isinstance(config, Config)

    def test_load_config_partial_data(self, tmp_path):
        config_dir = tmp_path / "vox"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"

        config_data = {"hotkey": {"trigger": "f1"}}
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config = load_config()
            assert config.hotkey.trigger == "f1"
            # Other fields should have defaults
            assert config.server.port == 9876


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_config(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config = Config(
                hotkey=HotkeyConfig(trigger="f2"),
                server=ServerConfig(port=5555),
                audio=AudioConfig(input_device="USB Mic"),
            )
            save_config(config)

            config_file = tmp_path / "vox" / "config.yaml"
            assert config_file.exists()

            with open(config_file) as f:
                saved_data = yaml.safe_load(f)

            assert saved_data["hotkey"]["trigger"] == "f2"
            assert saved_data["server"]["port"] == 5555
            assert saved_data["audio"]["input_device"] == "USB Mic"

    def test_save_config_creates_directory(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            config = Config()
            save_config(config)

            config_dir = tmp_path / "vox"
            assert config_dir.exists()
            assert (config_dir / "config.yaml").exists()


class TestCreateDefaultConfig:
    """Tests for create_default_config function."""

    def test_create_default_config(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            create_default_config()

            config_file = tmp_path / "vox" / "config.yaml"
            assert config_file.exists()

            content = config_file.read_text()
            assert "hotkey:" in content
            assert "ctrl+space" in content
            assert "server:" in content
            assert "model:" in content
            assert "audio:" in content

    def test_create_default_config_already_exists(self, tmp_path):
        config_dir = tmp_path / "vox"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text("existing: content")

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            create_default_config()

            # Should not overwrite existing file
            assert config_file.read_text() == "existing: content"

    def test_create_default_config_creates_directory(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            create_default_config()

            config_dir = tmp_path / "vox"
            assert config_dir.exists()
