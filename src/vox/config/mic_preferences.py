"""Microphone preference persistence."""

import hashlib
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from vox.config.schema import get_cache_dir


class MicPreference(BaseModel):
    """A single microphone preference."""

    selected_device: str
    last_seen: datetime = Field(default_factory=datetime.now)


class MicPreferences(BaseModel):
    """Container for microphone preferences by configuration fingerprint."""

    preferences: dict[str, MicPreference] = Field(default_factory=dict)


def get_mic_preferences_path() -> Path:
    """Get the microphone preferences file path."""
    return get_cache_dir() / "mic_preferences.yaml"


def load_mic_preferences() -> MicPreferences:
    """Load microphone preferences from file.

    Returns:
        MicPreferences object (empty if file doesn't exist)
    """
    path = get_mic_preferences_path()

    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return MicPreferences(**data)

    return MicPreferences()


def save_mic_preferences(prefs: MicPreferences) -> None:
    """Save microphone preferences to file.

    Args:
        prefs: MicPreferences object to save
    """
    path = get_mic_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict with ISO format datetimes
    data = {"preferences": {}}
    for fingerprint, pref in prefs.preferences.items():
        data["preferences"][fingerprint] = {
            "selected_device": pref.selected_device,
            "last_seen": pref.last_seen.isoformat(),
        }

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def compute_config_fingerprint(devices: list[dict]) -> str:
    """Compute a fingerprint for a set of audio devices.

    Args:
        devices: List of device info dicts (must have "name" key)

    Returns:
        16-character hex fingerprint
    """
    device_names = sorted(d["name"] for d in devices)
    return hashlib.sha256("|".join(device_names).encode()).hexdigest()[:16]


def get_device_by_name(devices: list[dict], name: str) -> dict | None:
    """Find a device by name.

    Args:
        devices: List of device info dicts
        name: Device name to find

    Returns:
        Device info dict or None if not found
    """
    for device in devices:
        if device["name"] == name:
            return device
    return None


def load_preferred_device_name(devices: list[dict]) -> str | None:
    """Look up the remembered microphone for the current hardware configuration.

    Args:
        devices: List of currently available devices

    Returns:
        The device name last selected for this exact set of devices, or None if
        this hardware configuration has never been seen before.
    """
    if not devices:
        return None

    fingerprint = compute_config_fingerprint(devices)
    prefs = load_mic_preferences()

    if fingerprint in prefs.preferences:
        return prefs.preferences[fingerprint].selected_device

    return None


def save_device_preference(devices: list[dict], device_name: str | None) -> None:
    """Remember the selected microphone for the current hardware configuration.

    Args:
        devices: List of currently available devices
        device_name: Device name to remember, or None to forget any saved
            preference for this configuration (reverting it to the system default)
    """
    if not devices:
        return

    fingerprint = compute_config_fingerprint(devices)
    prefs = load_mic_preferences()

    if device_name is None:
        if fingerprint not in prefs.preferences:
            return
        del prefs.preferences[fingerprint]
    else:
        prefs.preferences[fingerprint] = MicPreference(selected_device=device_name)

    save_mic_preferences(prefs)
