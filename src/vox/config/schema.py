"""Configuration schema using Pydantic."""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class HotkeyConfig(BaseModel):
    """Hotkey configuration."""

    trigger: str = "ctrl+space"


class ServerConfig(BaseModel):
    """Server connection configuration."""

    host: str = "localhost"
    port: int = 9876


class ModelConfig(BaseModel):
    """Model configuration."""

    default: str = "small.en"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    compute_type: str = "int8"


class AudioConfig(BaseModel):
    """Audio input configuration."""

    input_device: str | None = None


class OutputConfig(BaseModel):
    """Output configuration."""

    method: Literal["clipboard", "type", "both"] = "both"
    typing_method: Literal["paste", "type"] = "paste"


class OverlayConfig(BaseModel):
    """Overlay indicator configuration."""

    enabled: bool = True
    position: Literal["top-right", "top-center", "bottom-right"] = "top-right"


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str = Field(default="")

    def get_api_key(self) -> str:
        """Get API key, expanding environment variables."""
        if self.api_key.startswith("${") and self.api_key.endswith("}"):
            env_var = self.api_key[2:-1]
            return os.environ.get(env_var, "")
        return self.api_key


class AgentConfig(BaseModel):
    """Agent configuration."""

    enabled: bool = True
    keyword: str = "Agent"
    llm: LLMConfig = Field(default_factory=LLMConfig)


class Config(BaseModel):
    """Main configuration."""

    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)


def get_config_dir() -> Path:
    """Get the configuration directory."""
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(config_home) / "vox"


def get_cache_dir() -> Path:
    """Get the cache directory."""
    cache_home = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return Path(cache_home) / "vox"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.yaml"


def load_config() -> Config:
    """Load configuration from file, creating defaults if needed."""
    config_path = get_config_path()

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return Config(**data)

    return Config()


def save_config(config: Config) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False)


def create_default_config() -> None:
    """Create default configuration file if it doesn't exist."""
    config_path = get_config_path()

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        default_config = """\
# Vox configuration

hotkey:
  trigger: ctrl+space        # Hold to record

server:
  host: localhost            # Or remote GPU: gpu-server.local
  port: 9876

model:
  default: small.en          # Options: tiny.en, base.en, small.en, medium.en
  device: auto               # auto, cpu, cuda
  compute_type: int8

audio:
  input_device: null         # Microphone name, or null for system default

output:
  method: both               # clipboard, type, both
  typing_method: paste       # Ctrl+V approach

overlay:
  enabled: true              # Show visual indicator
  position: top-right        # top-right, top-center, bottom-right

agent:
  enabled: true
  keyword: Agent
  llm:
    provider: anthropic
    model: claude-sonnet-4-20250514
    api_key: ${ANTHROPIC_API_KEY}
"""
        with open(config_path, "w") as f:
            f.write(default_config)
