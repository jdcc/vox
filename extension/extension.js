/**
 * Vox GNOME Shell Extension
 *
 * Provides global hotkey detection and visual indicator for Vox speech-to-text.
 * Exposes D-Bus service for communication with the Python client.
 */

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
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
        this._monitorsChangedId = null;
    }

    create() {
        this._widget = new St.Widget({
            style_class: 'vox-indicator vox-indicator-hidden',
            width: 24,
            height: 24,
            opacity: 0,
            reactive: false,
        });

        // Make rotation behave as expected (center pivot)
        this._widget.set_pivot_point(0.5, 0.5);

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
            log(`Vox: Unknown state "${state}"`);
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
                if (this._widget)
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

            // Actually apply rotation (your earlier code advanced angle but never used it)
            this._widget.rotation_angle_z = this._rotationAngle;

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
            this._widget.opacity = visible ? 255 : 0;

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
        this._settingsChangedId = null;

        // IMPORTANT:
        // Main.wm.addKeybinding expects the settings key used by the binding name
        // to be a strv (type 'as') in the schema, e.g. ['<Control>space'].
        //
        // If your schema currently defines 'hotkey' as a string, change it to:
        // <key name="hotkey" type="as">
        //   <default>['&lt;Control&gt;space']</default>
        // </key>
        this._bindingName = 'hotkey';

        // Toggle semantics: each activation flips state.
        this._toggledOn = false;
    }

    enable(settings) {
        this._settings = settings;
        this._registerOrUpdateBinding();

        this._settingsChangedId = this._settings.connect(`changed::${this._bindingName}`, () => {
            this._registerOrUpdateBinding();
        });
    }

    _registerOrUpdateBinding() {
        // Remove first to avoid duplicates
        try {
            Main.wm.removeKeybinding(this._bindingName);
        } catch (_) {
            // ignore
        }

        Main.wm.addKeybinding(
            this._bindingName,
            this._settings,
            // Prevent holding Space from spamming activations
            Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            // Make it work in normal + overview; adjust if you want to exclude some modes
            Shell.ActionMode.ALL,
            () => this._onActivated()
        );

        // (Optional) log the configured accelerator for sanity
        // Note: only works if the key type is 'as' (strv).
        try {
            const accel = this._settings.get_strv(this._bindingName);
            log(`Vox: Keybinding "${this._bindingName}" registered: ${JSON.stringify(accel)}`);
        } catch (_) {
            log(`Vox: Keybinding "${this._bindingName}" registered (could not read as strv; check schema type)`);
        }
    }

    _onActivated() {
        // This gives you exactly:
        // Ctrl+Space (press) -> activation
        // release Space, keep holding Ctrl
        // press Space again -> activation again
        this._toggledOn = !this._toggledOn;

        if (this._toggledOn)
            this._onPress();
        else
            this._onRelease();
    }

    disable() {
        try {
            Main.wm.removeKeybinding(this._bindingName);
        } catch (_) {
            // ignore
        }

        if (this._settingsChangedId && this._settings) {
            this._settings.disconnect(this._settingsChangedId);
            this._settingsChangedId = null;
        }

        this._toggledOn = false;
    }
}

class VoxDBusService {
    constructor(indicator) {
        this._indicator = indicator;
        this._dbusId = null;
        this._connection = null;
        this._registrationId = null;
    }

    enable() {
        const nodeInfo = Gio.DBusNodeInfo.new_for_xml(DBUS_INTERFACE);

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
                    (conn, sender, path, iface, method, params, invocation) => {
                        if (method === 'SetState') {
                            const [state] = params.deep_unpack();
                            this._indicator.setState(state);
                            invocation.return_value(null);
                        } else if (method === 'GetState') {
                            const state = this._indicator.getState();
                            invocation.return_value(new GLib.Variant('(s)', [state]));
                        }
                    },
                    null,
                    null
                );
                log('Vox: D-Bus service registered');
            },
            (connection, name) => {
                // Name acquired
                log(`Vox: D-Bus name acquired: ${name}`);
            },
            (connection, name) => {
                // Name lost
                log(`Vox: D-Bus name lost: ${name}`);
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

        // Create hotkey handler (keybinding-based)
        this._hotkeyHandler = new VoxHotkeyHandler(
            () => this._dbusService.emitHotkeyPressed(),
            () => this._dbusService.emitHotkeyReleased()
        );
        this._hotkeyHandler.enable(this._settings);

        log('Vox: Extension enabled');
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

        log('Vox: Extension disabled');
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
            log('Vox: Schema not found. Please run: make install-extension');
            // Return a fake settings object to prevent crashes.
            // NOTE: This fake object is not sufficient for addKeybinding (expects get_strv),
            // but it prevents hard crashes during dev.
            return {
                get_strv: () => ['<Control>space'],
                connect: () => 0,
                disconnect: () => { },
            };
        }

        return new Gio.Settings({ settings_schema: schemaObj });
    }
}