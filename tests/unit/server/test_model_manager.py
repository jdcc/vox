"""Tests for vox.server.model_manager."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vox.server.model_manager import ModelManager


def test_get_model_path_missing(monkeypatch, tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path
    manager.models_db.get_model = MagicMock(return_value=None)

    assert manager.get_model_path("missing") is None


def test_get_model_path_exists(tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path
    model_dir = tmp_path / "small.en"
    model_dir.mkdir()
    manager.models_db.get_model = MagicMock(return_value=MagicMock())

    assert manager.get_model_path("small.en") == model_dir


def test_get_model_path_not_downloaded(tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path
    manager.models_db.get_model = MagicMock(return_value=MagicMock())

    assert manager.get_model_path("small.en") is None


def test_download_model_unknown() -> None:
    manager = ModelManager()
    manager.models_db.get_model = MagicMock(return_value=None)

    with pytest.raises(ValueError):
        manager.download_model("unknown")


def test_download_model_success(monkeypatch, tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path
    model_info = MagicMock(name="Small", repo="repo")
    manager.models_db.get_model = MagicMock(return_value=model_info)

    def download_stub(*_args, **_kwargs):
        return str(tmp_path / "small.en")

    monkeypatch.setattr("vox.server.model_manager.snapshot_download", download_stub)

    progress = []

    def progress_cb(msg):
        progress.append(msg)

    path = manager.download_model("small.en", progress_callback=progress_cb)

    assert path == tmp_path / "small.en"
    assert progress


def test_download_model_no_progress(monkeypatch, tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path
    model_info = MagicMock(name="Small", repo="repo")
    manager.models_db.get_model = MagicMock(return_value=model_info)

    def download_stub(*_args, **_kwargs):
        return str(tmp_path / "small.en")

    monkeypatch.setattr("vox.server.model_manager.snapshot_download", download_stub)

    path = manager.download_model("small.en")

    assert path == tmp_path / "small.en"


def test_ensure_model_downloads(monkeypatch, tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path
    manager.get_model_path = MagicMock(return_value=None)
    manager.download_model = MagicMock(return_value=tmp_path / "small.en")

    path = manager.ensure_model("small.en")

    assert path == tmp_path / "small.en"


def test_ensure_model_uses_existing(tmp_path) -> None:
    manager = ModelManager()
    manager.get_model_path = MagicMock(return_value=tmp_path / "small.en")

    assert manager.ensure_model("small.en") == tmp_path / "small.en"


def test_list_models() -> None:
    manager = ModelManager()
    manager.models_db.list_models = MagicMock(return_value=[MagicMock()])

    assert manager.list_models()


def test_list_downloaded_models() -> None:
    manager = ModelManager()
    manager.models_db.get_downloaded_models = MagicMock(return_value=[MagicMock()])

    assert manager.list_downloaded_models()


def test_delete_model_success(tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path
    model_dir = tmp_path / "small.en"
    model_dir.mkdir()

    assert manager.delete_model("small.en") is True
    assert not model_dir.exists()


def test_delete_model_missing(tmp_path) -> None:
    manager = ModelManager()
    manager.cache_dir = tmp_path

    assert manager.delete_model("small.en") is False
