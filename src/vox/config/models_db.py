"""Models database parser."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from vox.config.schema import get_cache_dir


@dataclass
class ModelInfo:
    """Information about a whisper model."""

    id: str
    name: str
    size: str
    repo: str

    def is_downloaded(self) -> bool:
        """Check if model is downloaded."""
        model_path = get_cache_dir() / "models" / self.id
        return model_path.exists()

    def get_path(self) -> Path:
        """Get the model cache path."""
        return get_cache_dir() / "models" / self.id


class ModelsDB:
    """Database of available whisper models."""

    def __init__(self) -> None:
        self.models: dict[str, ModelInfo] = {}
        self._load_models()

    def _load_models(self) -> None:
        """Load models from embedded YAML file."""
        models_yaml = Path(__file__).parent.parent.parent.parent / "config" / "models.yaml"

        if not models_yaml.exists():
            models_yaml = Path(__file__).parent.parent.parent.parent.parent / "config" / "models.yaml"

        if models_yaml.exists():
            with open(models_yaml) as f:
                data = yaml.safe_load(f)

            for model_data in data.get("models", []):
                model = ModelInfo(
                    id=model_data["id"],
                    name=model_data["name"],
                    size=model_data["size"],
                    repo=model_data["repo"],
                )
                self.models[model.id] = model

    def get_model(self, model_id: str) -> ModelInfo | None:
        """Get model info by ID."""
        return self.models.get(model_id)

    def list_models(self) -> list[ModelInfo]:
        """List all available models."""
        return list(self.models.values())

    def get_downloaded_models(self) -> list[ModelInfo]:
        """List downloaded models."""
        return [m for m in self.models.values() if m.is_downloaded()]
