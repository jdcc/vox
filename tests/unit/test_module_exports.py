"""Tests for package exports."""

import runpy

import vox
import vox.client as client_module
import vox.config as config_module
import vox.server as server_module


def test_version() -> None:
    assert vox.__version__


def test_client_exports() -> None:
    assert "AudioRecorder" in client_module.__all__
    assert client_module.AudioRecorder


def test_server_exports() -> None:
    assert "Transcriber" in server_module.__all__
    assert server_module.Transcriber


def test_config_exports() -> None:
    assert "Config" in config_module.__all__
    assert config_module.Config


def test_main_module_invokes_cli(monkeypatch) -> None:
    called = {"value": False}

    def main_stub():
        called["value"] = True

    monkeypatch.setattr("vox.cli.main", main_stub)

    runpy.run_module("vox.__main__", run_name="__main__")

    assert called["value"] is True
