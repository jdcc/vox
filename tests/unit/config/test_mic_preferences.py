"""Tests for microphone preference helpers."""

from datetime import datetime
from unittest.mock import patch

from vox.config.mic_preferences import (
    MicPreference,
    MicPreferences,
    compute_config_fingerprint,
    get_device_by_name,
    get_mic_preferences_path,
    load_mic_preferences,
    load_preferred_device_name,
    save_device_preference,
    save_mic_preferences,
)


def test_get_mic_preferences_path(tmp_path) -> None:
    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        assert get_mic_preferences_path() == tmp_path / "vox" / "mic_preferences.yaml"


def test_load_mic_preferences_missing_file(tmp_path) -> None:
    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        prefs = load_mic_preferences()
        assert prefs == MicPreferences()


def test_save_and_load_mic_preferences(tmp_path) -> None:
    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        prefs = MicPreferences(
            preferences={
                "abc123": MicPreference(
                    selected_device="USB Mic",
                    last_seen=datetime.fromisoformat("2024-01-02T03:04:05"),
                )
            }
        )

        save_mic_preferences(prefs)
        loaded = load_mic_preferences()

        assert loaded.preferences["abc123"].selected_device == "USB Mic"
        assert loaded.preferences["abc123"].last_seen == datetime.fromisoformat(
            "2024-01-02T03:04:05"
        )


def test_compute_config_fingerprint_is_order_independent() -> None:
    first = [{"name": "USB Mic"}, {"name": "Desk Mic"}]
    second = [{"name": "Desk Mic"}, {"name": "USB Mic"}]

    assert compute_config_fingerprint(first) == compute_config_fingerprint(second)


def test_get_device_by_name_returns_match() -> None:
    devices = [{"name": "USB Mic"}, {"name": "Desk Mic"}]

    assert get_device_by_name(devices, "Desk Mic") == {"name": "Desk Mic"}
    assert get_device_by_name(devices, "Missing") is None


def test_load_preferred_device_name_returns_saved_match(tmp_path) -> None:
    devices = [
        {"name": "USB Mic", "channels": 1, "sample_rate": 48000, "index": 0},
        {"name": "Desk Mic", "channels": 2, "sample_rate": 44100, "index": 1},
    ]

    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        fingerprint = compute_config_fingerprint(devices)
        save_mic_preferences(
            MicPreferences(
                preferences={fingerprint: MicPreference(selected_device="Desk Mic")}
            )
        )

        assert load_preferred_device_name(devices) == "Desk Mic"
        assert load_preferred_device_name([]) is None


def test_load_preferred_device_name_returns_none_when_unmatched(tmp_path) -> None:
    devices = [{"name": "USB Mic", "channels": 1, "sample_rate": 48000, "index": 0}]

    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        assert load_preferred_device_name(devices) is None


def test_save_device_preference_remembers_selection(tmp_path) -> None:
    devices = [{"name": "USB Mic", "channels": 1, "sample_rate": 48000, "index": 0}]

    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        save_device_preference(devices, "USB Mic")

        assert load_preferred_device_name(devices) == "USB Mic"


def test_save_device_preference_overwrites_existing_selection(tmp_path) -> None:
    devices = [{"name": "USB Mic", "channels": 1, "sample_rate": 48000, "index": 0}]

    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        save_device_preference(devices, "USB Mic")
        save_device_preference(devices, "Desk Mic")

        assert load_preferred_device_name(devices) == "Desk Mic"


def test_save_device_preference_none_forgets_selection(tmp_path) -> None:
    devices = [{"name": "USB Mic", "channels": 1, "sample_rate": 48000, "index": 0}]

    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        save_device_preference(devices, "USB Mic")
        save_device_preference(devices, None)

        assert load_preferred_device_name(devices) is None


def test_save_device_preference_none_when_nothing_saved_is_noop(tmp_path) -> None:
    devices = [{"name": "USB Mic", "channels": 1, "sample_rate": 48000, "index": 0}]

    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        save_device_preference(devices, None)

        assert not get_mic_preferences_path().exists()


def test_save_device_preference_no_devices_is_noop(tmp_path) -> None:
    with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
        save_device_preference([], "USB Mic")

        assert not get_mic_preferences_path().exists()
