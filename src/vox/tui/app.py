"""Textual TUI application for vox."""

import asyncio
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Select, Static, Switch

from vox.client.audio import list_audio_devices
from vox.config import (
    Config,
    ModelInfo,
    ModelsDB,
    get_device_by_name,
    load_config,
    load_legacy_selected_device_name,
    save_config,
)
from vox.server.model_manager import ModelManager


def _truncate(value: str, length: int) -> str:
    """Return a shortened display string."""
    if len(value) <= length:
        return value
    return value[: length - 3] + "..."


class SummaryPanel(Container):
    """Top-of-screen summary for the current dashboard state."""

    def compose(self) -> ComposeResult:
        yield Label(id="summary-primary")
        yield Label(id="summary-secondary")
        yield Label(id="summary-tertiary")

    def update_summary(
        self,
        config: Config,
        mic_label: str,
        device_count: int,
        message: str,
    ) -> None:
        """Update the displayed summary text."""
        self.query_one("#summary-primary", Label).update(
            f"Mic: {mic_label} | Model: {config.model.default} | Devices: {device_count}"
        )
        overlay_status = "on" if config.overlay.enabled else "off"
        self.query_one("#summary-secondary", Label).update(
            "Output: "
            f"{config.output.method}/{config.output.typing_method} | "
            f"Overlay: {overlay_status} ({config.overlay.position}) | "
            f"Hotkey: {config.hotkey.trigger}"
        )
        self.query_one("#summary-tertiary", Label).update(message)


class MicrophoneItem(ListItem):
    """List item for a microphone selection."""

    def __init__(
        self,
        device_name: str | None,
        display_name: str,
        details: str,
        *,
        selected: bool = False,
    ) -> None:
        self.device_name = device_name
        self.display_name = display_name
        self.details = details
        self._label = Label("")
        self._selected = selected
        super().__init__(self._label)
        self._refresh_label()

    def set_selected(self, selected: bool) -> None:
        """Update the selected state for the row."""
        self._selected = selected
        self._refresh_label()

    def _refresh_label(self) -> None:
        check = "[*]" if self._selected else "[ ]"
        name = _truncate(self.display_name, 28)
        self._label.update(f"{check} {name:<28} {self.details}")


class ModelItem(ListItem):
    """List item for a model selection."""

    def __init__(self, model: ModelInfo, *, selected: bool = False) -> None:
        self.model = model
        self._label = Label("")
        self._selected = selected
        super().__init__(self._label)
        self._refresh_label()

    def set_selected(self, selected: bool) -> None:
        """Update the selected state for the row."""
        self._selected = selected
        self._refresh_label()

    def _refresh_label(self) -> None:
        check = "[*]" if self._selected else "[ ]"
        downloaded = "Downloaded" if self.model.is_downloaded() else "Press d to download"
        self._label.update(
            f"{check} {self.model.id:<12} {self.model.size:<8} {downloaded}"
        )


class VoxApp(App):
    """Vox TUI application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    Header {
        dock: top;
    }

    #summary-panel {
        height: 4;
        margin: 0 1;
        padding: 0 1;
        border: round $primary;
        background: $surface;
    }

    #summary-primary {
        text-style: bold;
    }

    #summary-tertiary {
        color: $text-muted;
    }

    #main-content {
        height: 1fr;
        layout: horizontal;
        margin: 0 1 1 1;
    }

    #microphones-panel,
    #models-panel,
    #settings-panel {
        border: round $panel;
        background: $surface;
    }

    #microphones-panel:focus-within,
    #models-panel:focus-within,
    #settings-panel:focus-within {
        border: round $accent;
    }

    #microphones-panel {
        width: 2fr;
        margin-right: 1;
    }

    #sidebar {
        width: 3fr;
        layout: vertical;
    }

    #models-panel {
        height: 11;
        margin-bottom: 1;
    }

    #settings-panel {
        height: 1fr;
    }

    .panel-title {
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    .panel-subtitle {
        color: $text-muted;
        padding: 0 1;
    }

    ListView {
        height: 1fr;
        padding: 0 1 1 1;
    }

    ListItem {
        padding: 0 1;
    }

    #settings-grid {
        padding: 0 1 1 1;
    }

    .setting-group {
        margin-top: 1;
    }

    .setting-label {
        margin-top: 1;
        color: $text-muted;
    }

    Switch,
    Select,
    Input {
        width: 1fr;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("i", "focus_microphones", "Microphones"),
        Binding("m", "focus_models", "Models"),
        Binding("s", "focus_settings", "Settings"),
        Binding("r", "refresh_microphones", "Refresh Mics"),
        Binding("d", "download_model", "Download"),
        Binding("tab", "focus_next", show=False),
        Binding("shift+tab", "focus_previous", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.models_db = ModelsDB()
        self.model_manager = ModelManager()
        self.devices: list[dict] = []
        self._selected_mic_name: str | None = None
        self._legacy_mic_name: str | None = None
        self._missing_mic_name: str | None = None
        self._banner_message = ""
        self._suspend_control_events = True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield SummaryPanel(id="summary-panel")
        yield Container(
            Container(
                Static("Microphones", classes="panel-title"),
                Static(
                    "Enter selects. r rescans. System default is always available.",
                    classes="panel-subtitle",
                ),
                ListView(id="microphones-list"),
                id="microphones-panel",
            ),
            Container(
                Container(
                    Static("Models", classes="panel-title"),
                    Static(
                        "Enter sets default. d downloads the highlighted model.",
                        classes="panel-subtitle",
                    ),
                    ListView(id="models-list"),
                    id="models-panel",
                ),
                Container(
                    Static("Core Settings", classes="panel-title"),
                    Static(
                        "Most changes affect the next client/server start. "
                        "Hotkey saves on Enter or blur.",
                        classes="panel-subtitle",
                    ),
                    Container(
                        Label("Output method", classes="setting-label"),
                        Select(
                            [
                                ("Clipboard and typing", "both"),
                                ("Clipboard only", "clipboard"),
                                ("Typing only", "type"),
                            ],
                            allow_blank=False,
                            value=self.config.output.method,
                            id="output-method-select",
                        ),
                        Label("Typing method", classes="setting-label"),
                        Select(
                            [
                                ("Paste", "paste"),
                                ("Type", "type"),
                            ],
                            allow_blank=False,
                            value=self.config.output.typing_method,
                            id="typing-method-select",
                        ),
                        Label("Overlay enabled", classes="setting-label"),
                        Switch(value=self.config.overlay.enabled, id="overlay-enabled-switch"),
                        Label("Overlay position", classes="setting-label"),
                        Select(
                            [
                                ("Top right", "top-right"),
                                ("Top center", "top-center"),
                                ("Bottom right", "bottom-right"),
                            ],
                            allow_blank=False,
                            value=self.config.overlay.position,
                            id="overlay-position-select",
                        ),
                        Label("Hotkey", classes="setting-label"),
                        Input(
                            value=self.config.hotkey.trigger,
                            placeholder="ctrl+space",
                            id="hotkey-input",
                        ),
                        id="settings-grid",
                    ),
                    id="settings-panel",
                ),
                id="sidebar",
            ),
            id="main-content",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Populate the dashboard and focus the microphone list."""
        self.refresh_microphones(show_message=False)
        self.refresh_models()
        self._sync_setting_controls()
        self._update_summary()
        self.query_one("#microphones-list", ListView).focus()
        self._suspend_control_events = False

    def action_focus_microphones(self) -> None:
        """Focus the microphone list."""
        self.query_one("#microphones-list", ListView).focus()

    def action_focus_models(self) -> None:
        """Focus the model list."""
        self.query_one("#models-list", ListView).focus()

    def action_focus_settings(self) -> None:
        """Focus the first control in the settings panel."""
        self.query_one("#output-method-select", Select).focus()

    def action_focus_next(self) -> None:
        """Move focus to the next widget."""
        self.screen.focus_next()

    def action_focus_previous(self) -> None:
        """Move focus to the previous widget."""
        self.screen.focus_previous()

    def action_refresh_microphones(self) -> None:
        """Rescan audio devices."""
        self.refresh_microphones(show_message=True)

    def refresh_microphones(self, *, show_message: bool) -> None:
        """Reload the microphone list from the current audio devices."""
        self.devices = list_audio_devices()
        self._legacy_mic_name = load_legacy_selected_device_name(self.devices)
        self._missing_mic_name = None

        configured_name = self.config.audio.input_device
        selected_name: str | None = None
        if configured_name:
            if get_device_by_name(self.devices, configured_name):
                selected_name = configured_name
            else:
                self._missing_mic_name = configured_name
        elif self._legacy_mic_name and get_device_by_name(self.devices, self._legacy_mic_name):
            selected_name = self._legacy_mic_name

        self._selected_mic_name = selected_name

        items = [
            MicrophoneItem(
                None,
                "System default",
                "Automatic device selection",
                selected=selected_name is None,
            )
        ]
        for device in self.devices:
            items.append(
                MicrophoneItem(
                    device["name"],
                    device["name"],
                    f"{device['channels']}ch {int(device['sample_rate'])}Hz",
                    selected=device["name"] == selected_name,
                )
            )

        list_view = self.query_one("#microphones-list", ListView)
        list_view.clear()
        list_view.extend(items)
        list_view.index = self._microphone_index_for(selected_name)

        if show_message:
            self._set_banner(
                f"Microphone list refreshed. Found {len(self.devices)} input device(s)."
            )
        else:
            self._update_summary()

    def refresh_models(self) -> None:
        """Reload the models list."""
        items = [
            ModelItem(model, selected=model.id == self.config.model.default)
            for model in self.models_db.list_models()
        ]
        list_view = self.query_one("#models-list", ListView)
        list_view.clear()
        list_view.extend(items)
        list_view.index = self._model_index_for(self.config.model.default)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        if event.list_view.id == "microphones-list" and isinstance(event.item, MicrophoneItem):
            self._select_microphone(event.item.device_name)
            return

        if event.list_view.id == "models-list" and isinstance(event.item, ModelItem):
            self._select_model(event.item.model)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Persist select widget changes."""
        if self._suspend_control_events:
            return

        if event.select.id == "output-method-select":
            self.config.output.method = str(event.value)
            self._sync_setting_controls()
            self._persist_config("Output method updated.")
            return

        if event.select.id == "typing-method-select":
            self.config.output.typing_method = str(event.value)
            self._persist_config("Typing method updated.")
            return

        if event.select.id == "overlay-position-select":
            self.config.overlay.position = str(event.value)
            self._persist_config("Overlay position updated.")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Persist switch widget changes."""
        if self._suspend_control_events:
            return

        if event.switch.id == "overlay-enabled-switch":
            self.config.overlay.enabled = event.value
            self._sync_setting_controls()
            self._persist_config("Overlay setting updated.")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Save input-backed settings on submit."""
        if event.input.id == "hotkey-input":
            self._save_hotkey(event.value)

    def on_input_blurred(self, event: Input.Blurred) -> None:
        """Save input-backed settings on blur."""
        if event.input.id == "hotkey-input":
            self._save_hotkey(event.value)

    def action_download_model(self) -> None:
        """Download the highlighted model."""
        list_view = self.query_one("#models-list", ListView)
        item = list_view.highlighted_child
        if not isinstance(item, ModelItem):
            self._set_banner("Focus a model to download it.")
            self.notify("Focus a model to download it.")
            return

        if item.model.is_downloaded():
            self._set_banner(f"{item.model.id} is already downloaded.")
            self.notify(f"{item.model.id} is already downloaded.")
            return

        self._set_banner(f"Downloading {item.model.id}...")
        self.notify(f"Downloading {item.model.id}...")
        self.run_worker(
            self._download_model(item.model),
            name=f"download-{item.model.id}",
        )

    async def _download_model(self, model: ModelInfo) -> None:
        """Download a model without blocking the UI."""
        try:
            await asyncio.to_thread(self.model_manager.download_model, model.id)
        except Exception as exc:
            self._set_banner(f"Download failed for {model.id}: {exc}")
            self.notify(f"Download failed: {exc}", severity="error")
            return

        self.refresh_models()
        self._set_banner(f"Downloaded {model.id}. Press Enter to make it the default model.")
        self.notify(f"Downloaded {model.id}.")

    def _select_microphone(self, device_name: str | None) -> None:
        """Persist the selected microphone."""
        self.config.audio.input_device = device_name
        self._selected_mic_name = device_name
        self._missing_mic_name = None
        self._sync_microphone_selection()

        if device_name is None:
            self._persist_config("Microphone reset to system default.")
            return

        self._persist_config(f"Microphone set to {device_name}.")

    def _select_model(self, model: ModelInfo) -> None:
        """Persist the selected model when it is available locally."""
        if not model.is_downloaded():
            self._set_banner(f"{model.id} is not downloaded. Press d to download it first.")
            self.notify(f"{model.id} is not downloaded yet. Press d to download it.")
            return

        self.config.model.default = model.id
        self._sync_model_selection()
        self._persist_config(f"Default model set to {model.id}.")

    def _save_hotkey(self, value: str) -> None:
        """Persist a new hotkey when it is valid."""
        if self._suspend_control_events:
            return

        stripped = value.strip()
        hotkey_input = self.query_one("#hotkey-input", Input)

        if not stripped:
            hotkey_input.value = self.config.hotkey.trigger
            self._set_banner("Hotkey cannot be empty.")
            self.notify("Hotkey cannot be empty.", severity="error")
            return

        if stripped == self.config.hotkey.trigger:
            return

        self.config.hotkey.trigger = stripped
        hotkey_input.value = stripped
        self._persist_config("Hotkey updated.")

    def _persist_config(self, message: str) -> None:
        """Save the current config and update dashboard messaging."""
        save_config(self.config)
        self._set_banner(f"{message} Applies on the next client/server start.")
        self.notify(message)

    def _set_banner(self, message: str) -> None:
        """Store a banner message and refresh the summary."""
        self._banner_message = message
        self._update_summary()

    def _update_summary(self) -> None:
        """Refresh the top summary panel."""
        summary = self.query_one(SummaryPanel)
        summary.update_summary(
            self.config,
            self._selected_mic_label(),
            len(self.devices),
            self._status_message(),
        )

    def _status_message(self) -> str:
        """Return the current status or hint message."""
        if self._banner_message:
            return self._banner_message

        if self._missing_mic_name:
            return (
                f"Configured microphone '{self._missing_mic_name}' is unavailable. "
                "System default will be used until you pick another."
            )

        if self.config.audio.input_device is None and self._legacy_mic_name:
            return (
                f"Using legacy microphone selection '{self._legacy_mic_name}' "
                "until you save a new choice."
            )

        return "Enter selects, Tab moves focus, r refreshes devices, d downloads models."

    def _selected_mic_label(self) -> str:
        """Return the display label for the active microphone."""
        if self._selected_mic_name:
            is_legacy = self._legacy_mic_name == self._selected_mic_name
            if self.config.audio.input_device is None and is_legacy:
                return f"{self._selected_mic_name} (legacy)"
            return self._selected_mic_name

        if self._missing_mic_name:
            return f"System default [configured '{self._missing_mic_name}' missing]"

        return "System default"

    def _sync_microphone_selection(self) -> None:
        """Refresh microphone row checkmarks."""
        list_view = self.query_one("#microphones-list", ListView)
        for item in list_view.children:
            if isinstance(item, MicrophoneItem):
                item.set_selected(item.device_name == self._selected_mic_name)
                if item.device_name is None and self._selected_mic_name is None:
                    item.set_selected(True)
        list_view.index = self._microphone_index_for(self._selected_mic_name)
        self._update_summary()

    def _sync_model_selection(self) -> None:
        """Refresh model row checkmarks."""
        list_view = self.query_one("#models-list", ListView)
        for item in list_view.children:
            if isinstance(item, ModelItem):
                item.set_selected(item.model.id == self.config.model.default)
        list_view.index = self._model_index_for(self.config.model.default)
        self._update_summary()

    def _sync_setting_controls(self) -> None:
        """Enable or disable controls based on current selections."""
        typing_select = self.query_one("#typing-method-select", Select)
        overlay_position = self.query_one("#overlay-position-select", Select)
        typing_select.disabled = self.config.output.method == "clipboard"
        overlay_position.disabled = not self.config.overlay.enabled

    def _microphone_index_for(self, device_name: str | None) -> int:
        """Return the index for a microphone row."""
        if device_name is None:
            return 0

        for index, device in enumerate(self.devices, start=1):
            if device["name"] == device_name:
                return index

        return 0

    def _model_index_for(self, model_id: str) -> int:
        """Return the index for a model row."""
        for index, model in enumerate(self.models_db.list_models()):
            if model.id == model_id:
                return index
        return 0


def run_tui() -> None:
    """Run the TUI application."""
    app = VoxApp()
    app.run()
