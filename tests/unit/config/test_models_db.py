"""Tests for vox.config.models_db module."""

import io
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from vox.config.models_db import ModelInfo, ModelsDB


class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_create_model_info(self):
        model = ModelInfo(
            id="tiny.en",
            name="Tiny (English)",
            size="75MB",
            repo="Systran/faster-whisper-tiny.en",
        )
        assert model.id == "tiny.en"
        assert model.name == "Tiny (English)"
        assert model.size == "75MB"
        assert model.repo == "Systran/faster-whisper-tiny.en"

    def test_is_downloaded_false(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
            model = ModelInfo(
                id="test-model",
                name="Test Model",
                size="100MB",
                repo="test/repo",
            )
            assert model.is_downloaded() is False

    def test_is_downloaded_true(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
            # Create the model directory
            model_dir = tmp_path / "vox" / "models" / "test-model"
            model_dir.mkdir(parents=True)

            model = ModelInfo(
                id="test-model",
                name="Test Model",
                size="100MB",
                repo="test/repo",
            )
            assert model.is_downloaded() is True

    def test_get_path(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
            model = ModelInfo(
                id="test-model",
                name="Test Model",
                size="100MB",
                repo="test/repo",
            )
            expected_path = tmp_path / "vox" / "models" / "test-model"
            assert model.get_path() == expected_path


class TestModelsDB:
    """Tests for ModelsDB class."""

    def test_load_models_from_yaml(self, tmp_path):
        # The ModelsDB looks for models.yaml relative to the source file
        # We'll test with the actual models.yaml file
        db = ModelsDB()
        # Should load models from config/models.yaml
        assert len(db.models) > 0

    def test_get_model_exists(self):
        db = ModelsDB()
        # Assuming tiny.en exists in models.yaml
        model = db.get_model("tiny.en")
        assert model is not None
        assert model.id == "tiny.en"

    def test_get_model_not_exists(self):
        db = ModelsDB()
        model = db.get_model("nonexistent-model")
        assert model is None

    def test_list_models(self):
        db = ModelsDB()
        models = db.list_models()
        assert isinstance(models, list)
        assert len(models) > 0
        assert all(isinstance(m, ModelInfo) for m in models)

    def test_get_downloaded_models_none(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
            db = ModelsDB()
            downloaded = db.get_downloaded_models()
            assert downloaded == []

    def test_get_downloaded_models_some(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
            db = ModelsDB()

            # Create a "downloaded" model directory
            if db.models:
                first_model_id = list(db.models.keys())[0]
                model_dir = tmp_path / "vox" / "models" / first_model_id
                model_dir.mkdir(parents=True)

                downloaded = db.get_downloaded_models()
                assert len(downloaded) == 1
                assert downloaded[0].id == first_model_id


class TestModelsDBLoading:
    """Tests for ModelsDB file loading edge cases."""

    def test_models_db_loads_all_fields(self):
        db = ModelsDB()
        if db.models:
            model = list(db.models.values())[0]
            # Verify all fields are populated
            assert model.id
            assert model.name
            assert model.size
            assert model.repo

    def test_models_db_model_ids_unique(self):
        db = ModelsDB()
        ids = [m.id for m in db.list_models()]
        assert len(ids) == len(set(ids)), "Model IDs should be unique"

    def test_models_db_fallback_path(self, monkeypatch):
        import vox.config.models_db as models_db_module

        base = models_db_module.Path(models_db_module.__file__).parent.parent.parent.parent
        first = base / "config" / "models.yaml"
        second = base.parent / "config" / "models.yaml"

        def exists_stub(self):
            if self == first:
                return False
            if self == second:
                return True
            return False

        monkeypatch.setattr(models_db_module.Path, "exists", exists_stub)
        monkeypatch.setattr(
            "builtins.open",
            lambda *_args, **_kwargs: io.StringIO(
                "models:\n  - id: test\n    name: Test\n    size: 1MB\n    repo: test/repo\n"
            ),
        )

        db = ModelsDB()
        assert db.get_model("test") is not None

    def test_models_db_missing_file(self, monkeypatch):
        import vox.config.models_db as models_db_module

        monkeypatch.setattr(models_db_module.Path, "exists", lambda _self: False)

        db = ModelsDB()
        assert db.models == {}
