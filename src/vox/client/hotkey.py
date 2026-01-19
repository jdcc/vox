"""Global hotkey handling using evdev for Wayland."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Callable

import evdev
from evdev import InputDevice, categorize, ecodes

logger = logging.getLogger(__name__)

KEY_MAPPING = {
    "ctrl": {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL},
    "alt": {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT},
    "shift": {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT},
    "super": {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA},
    "meta": {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA},
    "space": {ecodes.KEY_SPACE},
    "enter": {ecodes.KEY_ENTER},
    "tab": {ecodes.KEY_TAB},
    "escape": {ecodes.KEY_ESC},
    "esc": {ecodes.KEY_ESC},
}

for c in "abcdefghijklmnopqrstuvwxyz":
    key_code = getattr(ecodes, f"KEY_{c.upper()}")
    KEY_MAPPING[c] = {key_code}

for i in range(10):
    KEY_MAPPING[str(i)] = {getattr(ecodes, f"KEY_{i}")}

for i in range(1, 13):
    KEY_MAPPING[f"f{i}"] = {getattr(ecodes, f"KEY_F{i}")}


def parse_hotkey(hotkey_str: str) -> tuple[set[int], set[int]]:
    """Parse a hotkey string into modifier and key sets.

    Args:
        hotkey_str: Hotkey string like "ctrl+space" or "ctrl+shift+a"

    Returns:
        Tuple of (modifier_keys, trigger_keys)
    """
    parts = hotkey_str.lower().split("+")
    modifiers = set()
    triggers = set()

    modifier_names = {"ctrl", "alt", "shift", "super", "meta"}

    for part in parts:
        part = part.strip()
        if part in modifier_names:
            modifiers.update(KEY_MAPPING.get(part, set()))
        else:
            triggers.update(KEY_MAPPING.get(part, set()))

    return modifiers, triggers


def find_keyboard_devices() -> list[InputDevice]:
    """Find all keyboard input devices.

    Returns:
        List of keyboard InputDevice objects
    """
    devices = []
    input_dir = Path("/dev/input")

    for event_path in input_dir.glob("event*"):
        try:
            device = InputDevice(str(event_path))
            capabilities = device.capabilities()

            if ecodes.EV_KEY in capabilities:
                keys = capabilities[ecodes.EV_KEY]
                if ecodes.KEY_A in keys and ecodes.KEY_SPACE in keys:
                    devices.append(device)
                    logger.debug(f"Found keyboard: {device.name}")
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot access {event_path}: {e}")

    return devices


class HotkeyListener:
    """Listens for global hotkeys using evdev."""

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        """Initialize the hotkey listener.

        Args:
            hotkey: Hotkey string (e.g., "ctrl+space")
            on_press: Callback when hotkey is pressed
            on_release: Callback when hotkey is released
        """
        self.modifiers, self.triggers = parse_hotkey(hotkey)
        self.on_press = on_press
        self.on_release = on_release

        self._devices: list[InputDevice] = []
        self._pressed_keys: set[int] = set()
        self._hotkey_active = False
        self._running = False
        self._tasks: list[asyncio.Task] = []

    def _check_hotkey_state(self) -> bool:
        """Check if the hotkey combination is currently pressed.

        Returns:
            True if hotkey is active
        """
        modifiers_pressed = all(
            any(mod in self._pressed_keys for mod in KEY_MAPPING.get(name, set()))
            for name, codes in KEY_MAPPING.items()
            if codes & self.modifiers
        )

        has_modifiers = bool(self.modifiers)
        if has_modifiers:
            modifiers_pressed = any(
                key in self._pressed_keys for key in self.modifiers
            )

        triggers_pressed = any(key in self._pressed_keys for key in self.triggers)

        return modifiers_pressed and triggers_pressed

    async def _handle_device(self, device: InputDevice) -> None:
        """Handle events from a single device.

        Args:
            device: The input device to read from
        """
        try:
            async for event in device.async_read_loop():
                if not self._running:
                    break

                if event.type != ecodes.EV_KEY:
                    continue

                key_event = categorize(event)

                if key_event.keystate == key_event.key_down:
                    self._pressed_keys.add(event.code)
                elif key_event.keystate == key_event.key_up:
                    self._pressed_keys.discard(event.code)

                hotkey_pressed = self._check_hotkey_state()

                if hotkey_pressed and not self._hotkey_active:
                    self._hotkey_active = True
                    logger.debug("Hotkey pressed")
                    self.on_press()
                elif not hotkey_pressed and self._hotkey_active:
                    self._hotkey_active = False
                    logger.debug("Hotkey released")
                    self.on_release()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading device {device.name}: {e}")

    async def start(self) -> None:
        """Start listening for hotkeys."""
        self._devices = find_keyboard_devices()

        if not self._devices:
            raise RuntimeError(
                "No keyboard devices found. Make sure you're in the 'input' group: "
                "sudo usermod -aG input $USER (then log out and back in)"
            )

        logger.info(f"Listening on {len(self._devices)} keyboard device(s)")
        self._running = True

        for device in self._devices:
            task = asyncio.create_task(self._handle_device(device))
            self._tasks.append(task)

    async def stop(self) -> None:
        """Stop listening for hotkeys."""
        self._running = False

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        for device in self._devices:
            try:
                device.close()
            except Exception:
                pass

        self._devices.clear()
        logger.info("Hotkey listener stopped")


def check_input_permissions() -> bool:
    """Check if the current user has permission to read input devices.

    Returns:
        True if permissions are sufficient
    """
    import grp
    import pwd

    try:
        user = pwd.getpwuid(os.getuid())
        groups = [g.gr_name for g in grp.getgrall() if user.pw_name in g.gr_mem]

        gid = os.getgid()
        primary_group = grp.getgrgid(gid).gr_name
        groups.append(primary_group)

        return "input" in groups
    except Exception as e:
        logger.error(f"Error checking permissions: {e}")
        return False
