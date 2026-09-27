"""Tests for the vox TUI dashboard."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from textual.widgets import Input, Label, Select, Switch

from vox.config.schema import (
    AudioConfig,
    Config,
    HotkeyConfig,
    ModelConfig,
    OutputConfig,
    OverlayConfig,
)
from vox.tui.app import VoxApp


@dataclass
class FakeModel:
    """Simple stand-in for model metadata in TUI tests."""

    id: str
    name: str
    size: str
    downloaded: bool = True

    def is_downloaded(self) -> bool:
        return self.downloaded


class FakeModelsDB:
    """Static model list for the TUI tests."""

    def __init__(self, models: list[FakeModel]) -> None:
        self._models = models

    def list_models(self) -> list[FakeModel]:
        return self._models


def make_config() -> Config:
    """Build a config object for the dashboard tests."""
    return Config(
        hotkey=HotkeyConfig(trigger="ctrl+space"),
        model=ModelConfig(default="small.en", device="cpu", compute_type="int8"),
        audio=AudioConfig(input_device=None),
        output=OutputConfig(method="both", typing_method="paste"),
        overlay=OverlayConfig(enabled=True, position="top-right"),
    )


def configure_app(monkeypatch, config: Config, models: list[FakeModel], devices: list[dict]):
    """Patch the TUI module dependencies and return a save log."""
    saved_configs: list[dict] = []
    saved_preferences: list[tuple[list[dict], str | None]] = []
    monkeypatch.setattr("vox.tui.app.load_config", lambda: config)
    monkeypatch.setattr(
        "vox.tui.app.save_config", lambda cfg: saved_configs.append(cfg.model_dump())
    )
    monkeypatch.setattr("vox.tui.app.list_audio_devices", lambda: devices)
    monkeypatch.setattr("vox.tui.app.load_preferred_device_name", lambda _devices: None)
    monkeypatch.setattr(
        "vox.tui.app.save_device_preference",
        lambda devs, name: saved_preferences.append((devs, name)),
    )
    monkeypatch.setattr("vox.tui.app.ModelsDB", lambda: FakeModelsDB(models))
    monkeypatch.setattr("vox.tui.app.ModelManager", lambda: MagicMock())
    return saved_configs, saved_preferences


@pytest.mark.asyncio
async def test_tui_selects_microphone_and_updates_summary(monkeypatch) -> None:
    config = make_config()
    devices = [
        {"name": "USB Mic", "channels": 1, "sample_rate": 48000},
        {"name": "Desk Mic", "channels": 2, "sample_rate": 44100},
    ]
    saved_configs, saved_preferences = configure_app(
        monkeypatch,
        config,
        [FakeModel("small.en", "Small", "488MB")],
        devices,
    )
    app = VoxApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()

        summary = str(app.query_one("#summary-primary", Label).render())

    # Selecting a microphone is now remembered per hardware configuration
    # rather than pinned globally in config.yaml.
    assert config.audio.input_device is None
    assert saved_configs[-1]["audio"]["input_device"] is None
    assert saved_preferences[-1] == (devices, "USB Mic")
    assert "USB Mic" in summary


@pytest.mark.asyncio
async def test_tui_resets_microphone_to_default(monkeypatch) -> None:
    config = make_config()
    config.audio.input_device = "USB Mic"
    devices = [{"name": "USB Mic", "channels": 1, "sample_rate": 48000}]
    saved_configs, saved_preferences = configure_app(
        monkeypatch,
        config,
        [FakeModel("small.en", "Small", "488MB")],
        devices,
    )
    app = VoxApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("up", "enter")
        await pilot.pause()

    assert config.audio.input_device is None
    assert saved_configs[-1]["audio"]["input_device"] is None
    assert saved_preferences[-1] == (devices, None)


@pytest.mark.asyncio
async def test_tui_selects_downloaded_model(monkeypatch) -> None:
    config = make_config()
    saved_configs, _saved_preferences = configure_app(
        monkeypatch,
        config,
        [
            FakeModel("small.en", "Small", "488MB", downloaded=True),
            FakeModel("medium.en", "Medium", "1.5GB", downloaded=True),
        ],
        [{"name": "USB Mic", "channels": 1, "sample_rate": 48000}],
    )
    app = VoxApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_focus_models()
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()

    assert config.model.default == "medium.en"
    assert saved_configs[-1]["model"]["default"] == "medium.en"


@pytest.mark.asyncio
async def test_tui_updates_core_settings(monkeypatch) -> None:
    config = make_config()
    saved_configs, _saved_preferences = configure_app(
        monkeypatch,
        config,
        [FakeModel("small.en", "Small", "488MB")],
        [{"name": "USB Mic", "channels": 1, "sample_rate": 48000}],
    )
    app = VoxApp()

    async with app.run_test() as pilot:
        await pilot.pause()

        output_select = app.query_one("#output-method-select", Select)
        typing_select = app.query_one("#typing-method-select", Select)
        overlay_switch = app.query_one("#overlay-enabled-switch", Switch)
        hotkey_input = app.query_one("#hotkey-input", Input)

        output_select.value = "clipboard"
        await pilot.pause()
        overlay_switch.value = False
        await pilot.pause()
        hotkey_input.focus()
        hotkey_input.value = "alt+r"
        await pilot.press("enter")
        await pilot.pause()

    assert config.output.method == "clipboard"
    assert typing_select.disabled is True
    assert config.overlay.enabled is False
    assert config.hotkey.trigger == "alt+r"
    assert saved_configs[-1]["hotkey"]["trigger"] == "alt+r"
