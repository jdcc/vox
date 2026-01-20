/**
 * Vox GNOME Shell Extension
 *
 * Provides global hotkey detection and visual indicator for Vox speech-to-text.
 * Exposes D-Bus service for communication with the Python client.
 */

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const DBUS_INTERFACE = `
<node>
  <interface name="org.vox.Extension">
    <method name="SetState">
      <arg type="s" name="state" direction="in"/>
    </method>
    <method name="GetState">
      <arg type="s" name="state" direction="out"/>
    </method>
    <signal name="HotkeyPressed"/>
    <signal name="HotkeyReleased"/>
  </interface>
</node>
`;

// State colors matching the original overlay
const STATE_COLORS = {
    recording: { r: 245, g: 66, b: 54 },    // #F54236
    processing: { r: 255, g: 193, b: 7 },   // #FFC107
    success: { r: 76, g: 175, b: 80 },      // #4CAF50
    failure: { r: 245, g: 66, b: 54 },      // #F54236
};

class VoxIndicator {
    constructor() {
        this._widget = null;
        this._state = 'hidden';
        this._animationTimeout = null;
        this._pulseDirection = 1;
        this._pulseValue = 1.0;
        this._rotationAngle = 0;
        this._flashCount = 0;
    }

    create() {
        this._widget = new St.Widget({
            style_class: 'vox-indicator vox-indicator-hidden',
            width: 24,
            height: 24,
            opacity: 0,
            reactive: false,
        });

        // Position in top-right corner
        this._updatePosition();

        Main.layoutManager.addChrome(this._widget, {
            affectsInputRegion: false,
            trackFullscreen: true,
        });

        // Update position when monitors change
        this._monitorsChangedId = Main.layoutManager.connect(
            'monitors-changed',
            () => this._updatePosition()
        );
    }

    _updatePosition() {
        if (!this._widget) return;

        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor) return;

        // Top-right corner with padding
        const padding = 16;
        this._widget.set_position(
            monitor.x + monitor.width - this._widget.width - padding,
            monitor.y + Main.panel.height + padding
        );
    }

    setState(state) {
        if (this._state === state) return;

        this._stopAnimation();
        this._state = state;

        if (state === 'hidden' || state === 'hide') {
            this._hide();
            return;
        }

        const color = STATE_COLORS[state];
        if (!color) {
            console.warn(`Vox: Unknown state "${state}"`);
            return;
        }

        this._widget.style = `
            background-color: rgb(${color.r}, ${color.g}, ${color.b});
            box-shadow: 0 0 8px rgba(${color.r}, ${color.g}, ${color.b}, 0.8);
            border-radius: 50%;
        `;
        this._widget.remove_style_class_name('vox-indicator-hidden');

        // Fade in
        this._widget.ease({
            opacity: 255,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });

        // Start state-specific animation
        if (state === 'recording') {
            this._startPulseAnimation();
        } else if (state === 'processing') {
            this._startSpinAnimation();
        } else if (state === 'success' || state === 'failure') {
            this._startFlashAnimation();
        }
    }

    _hide() {
        if (!this._widget) return;

        this._widget.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
            onComplete: () => {
                this._widget.add_style_class_name('vox-indicator-hidden');
            },
        });
    }

    _startPulseAnimation() {
        this._pulseValue = 1.0;
        this._pulseDirection = -1;

        const animate = () => {
            if (this._state !== 'recording' || !this._widget) return false;

            this._pulseValue += this._pulseDirection * 0.05;
            if (this._pulseValue <= 0.5) {
                this._pulseDirection = 1;
                this._pulseValue = 0.5;
            } else if (this._pulseValue >= 1.0) {
                this._pulseDirection = -1;
                this._pulseValue = 1.0;
            }

            const scale = 0.8 + (this._pulseValue * 0.4);
            this._widget.set_scale(scale, scale);

            return true;
        };

        this._animationTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, animate);
    }

    _startSpinAnimation() {
        this._rotationAngle = 0;

        const animate = () => {
            if (this._state !== 'processing' || !this._widget) return false;

            this._rotationAngle = (this._rotationAngle + 10) % 360;

            // Pulsing scale for processing
            const pulse = Math.sin(this._rotationAngle * Math.PI / 180) * 0.1 + 1.0;
            this._widget.set_scale(pulse, pulse);

            return true;
        };

        this._animationTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, animate);
    }

    _startFlashAnimation() {
        this._flashCount = 0;
        const maxFlashes = 3;

        const animate = () => {
            if (!this._widget) return false;

            this._flashCount++;

            if (this._flashCount >= maxFlashes * 2) {
                // Done flashing, hide
                this._hide();
                this._state = 'hidden';
                return false;
            }

            const visible = this._flashCount % 2 === 1;
            this._widget.opacity = visible ? 255 : 100;

            return true;
        };

        this._animationTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, animate);
    }

    _stopAnimation() {
        if (this._animationTimeout) {
            GLib.source_remove(this._animationTimeout);
            this._animationTimeout = null;
        }
        if (this._widget) {
            this._widget.set_scale(1, 1);
            this._widget.rotation_angle_z = 0;
        }
    }

    destroy() {
        this._stopAnimation();

        if (this._monitorsChangedId) {
            Main.layoutManager.disconnect(this._monitorsChangedId);
            this._monitorsChangedId = null;
        }

        if (this._widget) {
            Main.layoutManager.removeChrome(this._widget);
            this._widget.destroy();
            this._widget = null;
        }
    }

    getState() {
        return this._state;
    }
}

class VoxHotkeyHandler {
    constructor(onPress, onRelease) {
        this._onPress = onPress;
        this._onRelease = onRelease;
        this._settings = null;
        this._keyPressId = null;
        this._keyReleaseId = null;
        this._hotkeyActive = false;
        this._modifierKeys = new Set();
        this._triggerKey = null;
        this._pressedModifiers = new Set();
        this._triggerPressed = false;
    }

    enable(settings) {
        this._settings = settings;
        this._parseHotkey();

        // Connect to key events on global stage
        this._keyPressId = global.stage.connect('key-press-event',
            (actor, event) => this._onKeyPress(event));
        this._keyReleaseId = global.stage.connect('key-release-event',
            (actor, event) => this._onKeyRelease(event));

        // Re-parse hotkey when settings change
        this._settingsChangedId = this._settings.connect('changed::hotkey',
            () => this._parseHotkey());
    }

    _parseHotkey() {
        const hotkeyStr = this._settings.get_string('hotkey');

        // Parse GTK accelerator format (e.g., "<Control>space")
        this._modifierKeys.clear();
        this._triggerKey = null;

        // Extract modifiers
        if (hotkeyStr.includes('<Control>') || hotkeyStr.includes('<Ctrl>')) {
            this._modifierKeys.add(Clutter.KEY_Control_L);
            this._modifierKeys.add(Clutter.KEY_Control_R);
        }
        if (hotkeyStr.includes('<Shift>')) {
            this._modifierKeys.add(Clutter.KEY_Shift_L);
            this._modifierKeys.add(Clutter.KEY_Shift_R);
        }
        if (hotkeyStr.includes('<Alt>')) {
            this._modifierKeys.add(Clutter.KEY_Alt_L);
            this._modifierKeys.add(Clutter.KEY_Alt_R);
        }
        if (hotkeyStr.includes('<Super>')) {
            this._modifierKeys.add(Clutter.KEY_Super_L);
            this._modifierKeys.add(Clutter.KEY_Super_R);
        }

        // Extract trigger key (last part after all modifiers)
        const keyMatch = hotkeyStr.match(/[^<>]+$/);
        if (keyMatch) {
            const keyName = keyMatch[0].toLowerCase();
            // Map common key names to Clutter keysyms
            const keyMap = {
                'space': Clutter.KEY_space,
                'return': Clutter.KEY_Return,
                'enter': Clutter.KEY_Return,
                'tab': Clutter.KEY_Tab,
                'escape': Clutter.KEY_Escape,
            };

            this._triggerKey = keyMap[keyName] || Clutter[`KEY_${keyName}`];
        }

        console.log(`Vox: Hotkey configured - modifiers: ${this._modifierKeys.size}, trigger: ${this._triggerKey}`);
    }

    _isModifierKey(keyval) {
        return keyval === Clutter.KEY_Control_L || keyval === Clutter.KEY_Control_R ||
               keyval === Clutter.KEY_Shift_L || keyval === Clutter.KEY_Shift_R ||
               keyval === Clutter.KEY_Alt_L || keyval === Clutter.KEY_Alt_R ||
               keyval === Clutter.KEY_Super_L || keyval === Clutter.KEY_Super_R;
    }

    _checkHotkeyState() {
        // Check if required modifiers are pressed
        let modifiersPressed = true;
        if (this._modifierKeys.size > 0) {
            // Group modifiers by type (left/right variants)
            const ctrlPressed = this._pressedModifiers.has(Clutter.KEY_Control_L) ||
                               this._pressedModifiers.has(Clutter.KEY_Control_R);
            const shiftPressed = this._pressedModifiers.has(Clutter.KEY_Shift_L) ||
                                this._pressedModifiers.has(Clutter.KEY_Shift_R);
            const altPressed = this._pressedModifiers.has(Clutter.KEY_Alt_L) ||
                              this._pressedModifiers.has(Clutter.KEY_Alt_R);
            const superPressed = this._pressedModifiers.has(Clutter.KEY_Super_L) ||
                                this._pressedModifiers.has(Clutter.KEY_Super_R);

            const needsCtrl = this._modifierKeys.has(Clutter.KEY_Control_L);
            const needsShift = this._modifierKeys.has(Clutter.KEY_Shift_L);
            const needsAlt = this._modifierKeys.has(Clutter.KEY_Alt_L);
            const needsSuper = this._modifierKeys.has(Clutter.KEY_Super_L);

            modifiersPressed = (!needsCtrl || ctrlPressed) &&
                              (!needsShift || shiftPressed) &&
                              (!needsAlt || altPressed) &&
                              (!needsSuper || superPressed);
        }

        return modifiersPressed && this._triggerPressed;
    }

    _onKeyPress(event) {
        const keyval = event.get_key_symbol();

        if (this._isModifierKey(keyval)) {
            this._pressedModifiers.add(keyval);
        } else if (keyval === this._triggerKey) {
            this._triggerPressed = true;
        }

        const hotkeyPressed = this._checkHotkeyState();

        if (hotkeyPressed && !this._hotkeyActive) {
            this._hotkeyActive = true;
            this._onPress();
        }

        return Clutter.EVENT_PROPAGATE;
    }

    _onKeyRelease(event) {
        const keyval = event.get_key_symbol();

        if (this._isModifierKey(keyval)) {
            this._pressedModifiers.delete(keyval);
        } else if (keyval === this._triggerKey) {
            this._triggerPressed = false;
        }

        const hotkeyPressed = this._checkHotkeyState();

        if (!hotkeyPressed && this._hotkeyActive) {
            this._hotkeyActive = false;
            this._onRelease();
        }

        return Clutter.EVENT_PROPAGATE;
    }

    disable() {
        if (this._keyPressId) {
            global.stage.disconnect(this._keyPressId);
            this._keyPressId = null;
        }
        if (this._keyReleaseId) {
            global.stage.disconnect(this._keyReleaseId);
            this._keyReleaseId = null;
        }
        if (this._settingsChangedId && this._settings) {
            this._settings.disconnect(this._settingsChangedId);
            this._settingsChangedId = null;
        }

        this._hotkeyActive = false;
        this._pressedModifiers.clear();
        this._triggerPressed = false;
    }
}

class VoxDBusService {
    constructor(indicator) {
        this._indicator = indicator;
        this._dbusId = null;
        this._impl = null;
    }

    enable() {
        const nodeInfo = Gio.DBusNodeInfo.new_for_xml(DBUS_INTERFACE);

        this._impl = {
            SetState: (state) => {
                this._indicator.setState(state);
            },
            GetState: () => {
                return this._indicator.getState();
            },
        };

        this._dbusId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            'org.vox.Extension',
            Gio.BusNameOwnerFlags.NONE,
            (connection, name) => {
                // Bus acquired
                this._connection = connection;
                this._registrationId = connection.register_object(
                    '/org/vox/Extension',
                    nodeInfo.interfaces[0],
                    (connection, sender, path, iface, method, params, invocation) => {
                        if (method === 'SetState') {
                            const [state] = params.deep_unpack();
                            this._impl.SetState(state);
                            invocation.return_value(null);
                        } else if (method === 'GetState') {
                            const state = this._impl.GetState();
                            invocation.return_value(new GLib.Variant('(s)', [state]));
                        }
                    },
                    null,
                    null
                );
                console.log('Vox: D-Bus service registered');
            },
            (connection, name) => {
                // Name acquired
                console.log(`Vox: D-Bus name acquired: ${name}`);
            },
            (connection, name) => {
                // Name lost
                console.warn(`Vox: D-Bus name lost: ${name}`);
            }
        );
    }

    emitHotkeyPressed() {
        if (this._connection) {
            this._connection.emit_signal(
                null,
                '/org/vox/Extension',
                'org.vox.Extension',
                'HotkeyPressed',
                null
            );
        }
    }

    emitHotkeyReleased() {
        if (this._connection) {
            this._connection.emit_signal(
                null,
                '/org/vox/Extension',
                'org.vox.Extension',
                'HotkeyReleased',
                null
            );
        }
    }

    disable() {
        if (this._registrationId && this._connection) {
            this._connection.unregister_object(this._registrationId);
            this._registrationId = null;
        }
        if (this._dbusId) {
            Gio.bus_unown_name(this._dbusId);
            this._dbusId = null;
        }
        this._connection = null;
    }
}

export default class VoxExtension {
    constructor() {
        this._indicator = null;
        this._hotkeyHandler = null;
        this._dbusService = null;
        this._settings = null;
    }

    enable() {
        // Load settings
        this._settings = this._getSettings();

        // Create indicator
        this._indicator = new VoxIndicator();
        this._indicator.create();

        // Create D-Bus service
        this._dbusService = new VoxDBusService(this._indicator);
        this._dbusService.enable();

        // Create hotkey handler
        this._hotkeyHandler = new VoxHotkeyHandler(
            () => {
                this._dbusService.emitHotkeyPressed();
            },
            () => {
                this._dbusService.emitHotkeyReleased();
            }
        );
        this._hotkeyHandler.enable(this._settings);

        console.log('Vox: Extension enabled');
    }

    disable() {
        if (this._hotkeyHandler) {
            this._hotkeyHandler.disable();
            this._hotkeyHandler = null;
        }

        if (this._dbusService) {
            this._dbusService.disable();
            this._dbusService = null;
        }

        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }

        this._settings = null;

        console.log('Vox: Extension disabled');
    }

    _getSettings() {
        const schemaDir = GLib.build_filenamev([
            GLib.get_user_data_dir(),
            'gnome-shell',
            'extensions',
            'vox@local',
            'schemas'
        ]);

        let schemaSource;
        if (GLib.file_test(schemaDir, GLib.FileTest.EXISTS)) {
            schemaSource = Gio.SettingsSchemaSource.new_from_directory(
                schemaDir,
                Gio.SettingsSchemaSource.get_default(),
                false
            );
        } else {
            schemaSource = Gio.SettingsSchemaSource.get_default();
        }

        const schemaObj = schemaSource.lookup('org.gnome.shell.extensions.vox', true);
        if (!schemaObj) {
            console.error('Vox: Schema not found. Please run: make install-extension');
            // Return a fake settings object to prevent crashes
            return {
                get_string: () => '<Control>space',
                connect: () => 0,
                disconnect: () => {},
            };
        }

        return new Gio.Settings({ settings_schema: schemaObj });
    }
}
