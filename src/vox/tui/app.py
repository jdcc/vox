"""Textual TUI application for vox."""

from datetime import datetime
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import (
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

from vox.config import Config, load_config, ModelsDB, ModelInfo
from vox.server.model_manager import ModelManager


class StatusBar(Static):
    """Status bar showing connection and model info."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._status = "Disconnected"
        self._model = config.model.default

    def compose(self) -> ComposeResult:
        yield Label(f"Status: {self._status}  Model: {self._model}")
        yield Label(f"Hotkey: {self.config.hotkey.trigger} (hold to record)")

    def update_status(self, status: str) -> None:
        self._status = status
        self.refresh()

    def update_model(self, model: str) -> None:
        self._model = model
        self.refresh()


class ModelItem(ListItem):
    """List item for a model."""

    def __init__(self, model: ModelInfo, is_selected: bool = False) -> None:
        super().__init__()
        self.model = model
        self.is_selected = is_selected

    def compose(self) -> ComposeResult:
        check = "[*]" if self.is_selected else "[ ]"
        downloaded = "Downloaded" if self.model.is_downloaded() else "Not Downloaded"
        yield Label(
            f"  {check} {self.model.id:<12} {self.model.size:<8} {downloaded}"
        )


class ModelsPanel(Container):
    """Panel showing available models."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.models_db = ModelsDB()
        self.model_manager = ModelManager()

    def compose(self) -> ComposeResult:
        yield Static("[ Models ]", classes="panel-title")

        models = self.models_db.list_models()
        items = []
        for model in models:
            is_selected = model.id == self.config.model.default
            items.append(ModelItem(model, is_selected))

        yield ListView(*items, id="models-list")


class TranscriptionEntry(Static):
    """A single transcription entry."""

    def __init__(self, timestamp: str, text: str, is_agent: bool = False) -> None:
        super().__init__()
        self.timestamp = timestamp
        self.text = text
        self.is_agent = is_agent

    def compose(self) -> ComposeResult:
        if self.is_agent:
            yield Label(f"{self.timestamp}  Agent: {self.text}")
        else:
            yield Label(f"{self.timestamp}  {self.text}")


class TranscriptionsPanel(Container):
    """Panel showing recent transcriptions."""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[tuple[str, str, bool]] = []

    def compose(self) -> ComposeResult:
        yield Static("[ Transcriptions ]", classes="panel-title")
        yield Container(id="transcriptions-content")

    def add_entry(self, text: str, is_agent: bool = False) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        self.entries.append((timestamp, text, is_agent))

        content = self.query_one("#transcriptions-content", Container)
        content.mount(TranscriptionEntry(timestamp, text, is_agent))


class VoxApp(App):
    """Vox TUI application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    .panel-title {
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    #status-bar {
        height: 2;
        background: $surface;
        padding: 0 1;
    }

    #models-panel {
        height: 8;
        border: solid $primary;
    }

    #models-list {
        height: 100%;
    }

    #transcriptions-panel {
        height: 1fr;
        border: solid $primary;
    }

    #transcriptions-content {
        height: 100%;
        overflow-y: auto;
    }

    TranscriptionEntry {
        height: 1;
        padding: 0 1;
    }

    ModelItem {
        height: 1;
    }

    ModelItem:hover {
        background: $primary 30%;
    }

    Footer {
        background: $surface;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("m", "show_models", "Models"),
        Binding("s", "show_settings", "Settings"),
        Binding("q", "quit", "Quit"),
        Binding("d", "download_model", "Download"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.model_manager = ModelManager()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            StatusBar(self.config),
            id="status-bar",
        )
        yield Container(
            ModelsPanel(self.config),
            id="models-panel",
        )
        yield Container(
            TranscriptionsPanel(),
            id="transcriptions-panel",
        )
        yield Footer()

    def action_show_models(self) -> None:
        """Show models panel."""
        self.notify("Models panel focused")

    def action_show_settings(self) -> None:
        """Show settings."""
        self.notify("Settings not yet implemented")

    def action_download_model(self) -> None:
        """Download the selected model."""
        list_view = self.query_one("#models-list", ListView)
        if list_view.highlighted_child:
            item = list_view.highlighted_child
            if isinstance(item, ModelItem):
                model = item.model
                if not model.is_downloaded():
                    self.notify(f"Downloading {model.name}...")
                    self.run_worker(
                        self._download_model(model.id),
                        name=f"download-{model.id}",
                    )
                else:
                    self.notify(f"{model.name} already downloaded")

    async def _download_model(self, model_id: str) -> None:
        """Download a model in the background."""
        try:
            self.model_manager.download_model(
                model_id,
                progress_callback=lambda msg: self.notify(msg),
            )
            self.notify(f"Downloaded {model_id}")
            self.refresh()
        except Exception as e:
            self.notify(f"Download failed: {e}", severity="error")


def run_tui() -> None:
    """Run the TUI application."""
    app = VoxApp()
    app.run()
