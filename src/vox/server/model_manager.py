"""Model download and loading manager."""

import logging
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

from vox.config import ModelsDB, ModelInfo
from vox.config.schema import get_cache_dir

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages model downloading and loading."""

    def __init__(self) -> None:
        self.models_db = ModelsDB()
        self.cache_dir = get_cache_dir() / "models"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_model_path(self, model_id: str) -> Path | None:
        """Get the local path for a model, or None if not downloaded."""
        model_info = self.models_db.get_model(model_id)
        if model_info is None:
            return None

        model_path = self.cache_dir / model_id
        if model_path.exists():
            return model_path
        return None

    def download_model(
        self,
        model_id: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path:
        """Download a model from HuggingFace.

        Args:
            model_id: The model ID (e.g., "small.en")
            progress_callback: Optional callback for progress updates

        Returns:
            Path to the downloaded model

        Raises:
            ValueError: If model ID is not found
        """
        model_info = self.models_db.get_model(model_id)
        if model_info is None:
            raise ValueError(f"Unknown model: {model_id}")

        if progress_callback:
            progress_callback(f"Downloading {model_info.name}...")

        logger.info(f"Downloading model {model_id} from {model_info.repo}")

        model_path = snapshot_download(
            repo_id=model_info.repo,
            local_dir=self.cache_dir / model_id,
        )

        if progress_callback:
            progress_callback(f"Downloaded {model_info.name}")

        logger.info(f"Model downloaded to {model_path}")
        return Path(model_path)

    def ensure_model(
        self,
        model_id: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path:
        """Ensure a model is downloaded, downloading if necessary.

        Args:
            model_id: The model ID
            progress_callback: Optional callback for progress updates

        Returns:
            Path to the model
        """
        model_path = self.get_model_path(model_id)
        if model_path is not None:
            return model_path

        return self.download_model(model_id, progress_callback)

    def list_models(self) -> list[ModelInfo]:
        """List all available models."""
        return self.models_db.list_models()

    def list_downloaded_models(self) -> list[ModelInfo]:
        """List downloaded models."""
        return self.models_db.get_downloaded_models()

    def delete_model(self, model_id: str) -> bool:
        """Delete a downloaded model.

        Args:
            model_id: The model ID

        Returns:
            True if deleted, False if not found
        """
        model_path = self.cache_dir / model_id
        if model_path.exists():
            import shutil

            shutil.rmtree(model_path)
            logger.info(f"Deleted model {model_id}")
            return True
        return False
