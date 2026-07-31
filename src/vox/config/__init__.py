"""Configuration module for vox."""

from vox.config.mic_preferences import (
    MicPreference,
    MicPreferences,
    compute_config_fingerprint,
    get_device_by_name,
    get_mic_preferences_path,
    load_legacy_selected_device_name,
    load_mic_preferences,
    save_mic_preferences,
)
from vox.config.models_db import ModelInfo, ModelsDB
from vox.config.schema import (
    AudioConfig,
    Config,
    create_default_config,
    get_config_path,
    load_config,
    save_config,
)

__all__ = [
    "AudioConfig",
    "Config",
    "load_config",
    "save_config",
    "create_default_config",
    "get_config_path",
    "ModelsDB",
    "ModelInfo",
    "MicPreference",
    "MicPreferences",
    "compute_config_fingerprint",
    "get_device_by_name",
    "get_mic_preferences_path",
    "load_legacy_selected_device_name",
    "load_mic_preferences",
    "save_mic_preferences",
]
