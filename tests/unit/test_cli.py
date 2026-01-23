"""Tests for vox.cli commands."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

import vox.cli as cli_module


def test_setup_logging_verbose() -> None:
    cli_module.setup_logging(verbose=True)


def test_setup_logging_non_verbose() -> None:
    cli_module.setup_logging(verbose=False)


def test_version_option() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["--version"])
    assert result.exit_code == 0


def test_server_command(monkeypatch) -> None:
    runner = CliRunner()
    run_server = AsyncMock()
    monkeypatch.setattr("vox.server.app.run_server", run_server)

    def run_stub(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(asyncio, "run", run_stub)

    result = runner.invoke(cli_module.main, ["server", "--host", "127.0.0.1", "--port", "9999"])

    assert result.exit_code == 0
    run_server.assert_awaited_once_with("127.0.0.1", 9999)


def test_client_command(monkeypatch) -> None:
    runner = CliRunner()
    run_client = AsyncMock()
    monkeypatch.setattr("vox.client.app.run_client", run_client)

    def run_stub(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(asyncio, "run", run_stub)

    result = runner.invoke(cli_module.main, ["client"])

    assert result.exit_code == 0
    run_client.assert_awaited_once()


def test_tui_command(monkeypatch) -> None:
    runner = CliRunner()
    run_tui = MagicMock()
    monkeypatch.setattr("vox.tui.app.run_tui", run_tui)

    result = runner.invoke(cli_module.main, ["tui"])

    assert result.exit_code == 0
    run_tui.assert_called_once()


def test_transcribe_command(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    audio_file = tmp_path / "audio.wav"
    audio_file.write_text("data")

    config = MagicMock()
    config.model.default = "small.en"
    config.model.device = "cpu"
    config.model.compute_type = "int8"

    monkeypatch.setattr(cli_module, "load_config", MagicMock(return_value=config))
    transcriber = MagicMock()
    transcriber.transcribe.return_value = MagicMock(text="hello", duration=1.2)
    monkeypatch.setattr("vox.server.transcriber.Transcriber", MagicMock(return_value=transcriber))

    result = runner.invoke(cli_module.main, ["transcribe", str(audio_file), "--model", "tiny.en"])

    assert result.exit_code == 0
    assert "Transcription" in result.output


def test_models_list(monkeypatch) -> None:
    runner = CliRunner()
    db = MagicMock()
    db.list_models.return_value = [
        MagicMock(id="tiny.en", size="1MB", is_downloaded=lambda: False),
    ]
    monkeypatch.setattr(cli_module, "ModelsDB", MagicMock(return_value=db))

    result = runner.invoke(cli_module.main, ["models", "list"])

    assert result.exit_code == 0
    assert "tiny.en" in result.output


def test_models_download_unknown(monkeypatch) -> None:
    runner = CliRunner()
    manager = MagicMock()
    manager.models_db.get_model.return_value = None
    monkeypatch.setattr("vox.server.model_manager.ModelManager", MagicMock(return_value=manager))

    result = runner.invoke(cli_module.main, ["models", "download", "nope"])

    assert result.exit_code != 0
    assert "Unknown model" in result.output


def test_models_download_existing(monkeypatch) -> None:
    runner = CliRunner()
    model = MagicMock()
    model.is_downloaded.return_value = True
    manager = MagicMock()
    manager.models_db.get_model.return_value = model
    monkeypatch.setattr("vox.server.model_manager.ModelManager", MagicMock(return_value=manager))

    result = runner.invoke(cli_module.main, ["models", "download", "tiny.en"])

    assert result.exit_code == 0
    assert "already downloaded" in result.output


def test_models_download_success(monkeypatch) -> None:
    runner = CliRunner()
    model = MagicMock()
    model.is_downloaded.return_value = False
    model.name = "Tiny"
    model.size = "1MB"
    manager = MagicMock()
    manager.models_db.get_model.return_value = model
    def download_model_stub(_model_id, progress_callback=None):
        if progress_callback:
            progress_callback("downloading")
        return None
    manager.download_model.side_effect = download_model_stub
    monkeypatch.setattr("vox.server.model_manager.ModelManager", MagicMock(return_value=manager))

    result = runner.invoke(cli_module.main, ["models", "download", "tiny.en"])

    assert result.exit_code == 0
    manager.download_model.assert_called_once()


def test_models_delete_success(monkeypatch) -> None:
    runner = CliRunner()
    manager = MagicMock()
    manager.delete_model.return_value = True
    monkeypatch.setattr("vox.server.model_manager.ModelManager", MagicMock(return_value=manager))

    result = runner.invoke(cli_module.main, ["models", "delete", "tiny.en"], input="y\n")

    assert result.exit_code == 0
    assert "Deleted model" in result.output


def test_models_delete_missing(monkeypatch) -> None:
    runner = CliRunner()
    manager = MagicMock()
    manager.delete_model.return_value = False
    monkeypatch.setattr("vox.server.model_manager.ModelManager", MagicMock(return_value=manager))

    result = runner.invoke(cli_module.main, ["models", "delete", "tiny.en"], input="y\n")

    assert result.exit_code == 0
    assert "not found" in result.output


def test_config_show(monkeypatch) -> None:
    runner = CliRunner()
    config = MagicMock()
    config.model_dump.return_value = {"hotkey": {"trigger": "ctrl+space"}}
    monkeypatch.setattr(cli_module, "load_config", MagicMock(return_value=config))

    result = runner.invoke(cli_module.main, ["config", "show"])

    assert result.exit_code == 0
    assert "hotkey" in result.output


def test_config_path(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_module, "get_config_path", MagicMock(return_value=tmp_path / "config.yaml"))

    result = runner.invoke(cli_module.main, ["config", "path"])

    assert result.exit_code == 0


def test_config_init_no_overwrite(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing")

    monkeypatch.setattr(cli_module, "get_config_path", MagicMock(return_value=config_path))
    monkeypatch.setattr(cli_module, "create_default_config", MagicMock())
    monkeypatch.setattr(cli_module.click, "confirm", lambda _msg: False)

    result = runner.invoke(cli_module.main, ["config", "init"])

    assert result.exit_code == 0
    cli_module.create_default_config.assert_not_called()


def test_config_init_creates(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"

    monkeypatch.setattr(cli_module, "get_config_path", MagicMock(return_value=config_path))
    monkeypatch.setattr(cli_module, "create_default_config", MagicMock())

    result = runner.invoke(cli_module.main, ["config", "init"])

    assert result.exit_code == 0
    cli_module.create_default_config.assert_called_once()


def test_config_init_overwrite(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing")

    monkeypatch.setattr(cli_module, "get_config_path", MagicMock(return_value=config_path))
    monkeypatch.setattr(cli_module, "create_default_config", MagicMock())
    monkeypatch.setattr(cli_module.click, "confirm", lambda _msg: True)

    result = runner.invoke(cli_module.main, ["config", "init"])

    assert result.exit_code == 0
    cli_module.create_default_config.assert_called_once()


def test_check_command(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_module, "get_config_path", MagicMock(return_value=tmp_path / "config.yaml"))
    monkeypatch.setattr(
        "vox.client.output.check_wayland_tools",
        lambda: {"wl-copy": True, "wl-paste": True},
    )
    result = runner.invoke(cli_module.main, ["check"])

    assert result.exit_code == 0
    assert "Checking system dependencies" in result.output


def test_check_command_missing_tools(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("data")
    monkeypatch.setattr(cli_module, "get_config_path", MagicMock(return_value=config_path))
    monkeypatch.setattr(
        "vox.client.output.check_wayland_tools",
        lambda: {"wl-copy": False, "wl-paste": True},
    )
    result = runner.invoke(cli_module.main, ["check"])

    assert result.exit_code == 0
    assert "Install missing tools" in result.output


def test_check_command_all_tools_present(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("data")
    monkeypatch.setattr(cli_module, "get_config_path", MagicMock(return_value=config_path))
    monkeypatch.setattr(
        "vox.client.output.check_wayland_tools",
        lambda: {"wl-copy": True, "wl-paste": True},
    )
    result = runner.invoke(cli_module.main, ["check"])

    assert result.exit_code == 0
