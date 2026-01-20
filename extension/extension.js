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

// State colors (0.0-1.0 range for Cairo)
const STATE_COLORS = {
    recording:  { r: 1.0,   g: 0.392, b: 0.392 },  // rgba(255,100,100)
    processing: { r: 0.392, g: 0.627, b: 1.0   },  // rgba(100,160,255)
    success:    { r: 0.196, g: 0.784, b: 0.471 },  // rgba(50,200,120)
    failure:    { r: 1.0,   g: 0.392, b: 0.392 },  // rgba(255,100,100)
};

class VoxIndicator {
    constructor() {
        this._widget = null;
        this._state = 'hidden';
        this._prevState = null;
        this._animationTimeout = null;
        this._monitorsChangedId = null;

        // Animation timing
        this._time = 0;
        this._transitionProgress = 1;
        this._transitionDuration = 0.5;

        // Animation parameters (from HTML reference)
        this._animationSpeed = 0.8;
        this._opacityMultiplier = 1.1;
        this._lineThickness = 1.9;
        this._ringCount = 5;
        this._ringSpacing = 0.6;
        this._centerSize = 7;

        // Scale factor (100px widget / 300px source)
        this._scale = 1.5;
    }

    create() {
        this._widget = new St.DrawingArea({
            width: 210,
            height: 210,
            reactive: false,
        });

        this._widget.connect('repaint', this._onRepaint.bind(this));

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

    // Easing functions
    _inOutQuadEasing(t) {
        return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    }

    _outBackEasing(t) {
        const c1 = 1.70158;
        const c3 = c1 + 1;
        return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
    }

    setState(state) {
        if (this._state === state) return;

        // Handle 'hide' as alias for 'hidden'
        if (state === 'hide') state = 'hidden';

        // Validate state
        if (state !== 'hidden' && !STATE_COLORS[state]) {
            log(`Vox: Unknown state "${state}"`);
            return;
        }

        // Store previous state for crossfade
        this._prevState = this._state;
        this._state = state;
        this._transitionProgress = 0;

        // Start animation loop
        this._startAnimationLoop();
    }

    _startAnimationLoop() {
        if (this._animationTimeout) return;

        const frameInterval = 16;  // ~60fps
        const timeIncrement = 0.015;
        const transitionIncrement = 0.016;

        const animate = () => {
            if (!this._widget) return false;

            // Update time
            this._time += timeIncrement;

            // Update transition progress
            if (this._transitionProgress < 1) {
                const activeDuration = this._state === 'hidden' ? 0.2 : this._transitionDuration;
                this._transitionProgress += transitionIncrement / activeDuration;
                this._transitionProgress = Math.min(this._transitionProgress, 1);
            }

            // Request repaint
            this._widget.queue_repaint();

            // Stop animation loop if hidden and transition complete
            if (this._state === 'hidden' && this._transitionProgress >= 1) {
                this._animationTimeout = null;
                return false;
            }

            return true;
        };

        this._animationTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, frameInterval, animate);
    }

    _stopAnimationLoop() {
        if (this._animationTimeout) {
            GLib.source_remove(this._animationTimeout);
            this._animationTimeout = null;
        }
    }

    _onRepaint(area) {
        const cr = area.get_context();
        const [width, height] = area.get_surface_size();
        const cx = width / 2;
        const cy = height / 2;

        // Clear canvas
        cr.setOperator(0);  // CAIRO_OPERATOR_CLEAR
        cr.paint();
        cr.setOperator(2);  // CAIRO_OPERATOR_OVER

        // Calculate transition alpha
        const fadeProgress = this._inOutQuadEasing(this._transitionProgress);

        // Draw previous state fading out
        if (this._prevState && this._transitionProgress < 1) {
            const prevAlpha = 1 - fadeProgress;
            this._drawState(cr, this._prevState, cx, cy, prevAlpha);
        }

        // Draw current state fading in
        const currentAlpha = this._transitionProgress < 1 ? fadeProgress : 1;
        this._drawState(cr, this._state, cx, cy, currentAlpha);

        cr.$dispose();
    }

    _drawState(cr, state, cx, cy, alpha) {
        switch (state) {
            case 'recording':
                this._drawRecording(cr, cx, cy, alpha);
                break;
            case 'processing':
                this._drawProcessing(cr, cx, cy, alpha);
                break;
            case 'success':
                this._drawSuccess(cr, cx, cy, alpha);
                break;
            case 'failure':
                this._drawFailure(cr, cx, cy, alpha);
                break;
            case 'hidden':
                // Nothing to draw
                break;
        }
    }

    _drawRecording(cr, cx, cy, alpha) {
        const color = STATE_COLORS.recording;

        // 5 converging wave rings moving inward
        for (let i = 0; i < this._ringCount; i++) {
            const t = (this._time * this._animationSpeed * 5 + i * this._ringSpacing) % (Math.PI * 2);
            const radius = (50 - t * 7.96) * this._scale;
            const opacity = (t / (Math.PI * 2)) * 0.4 * this._opacityMultiplier * alpha;

            if (radius > 0) {
                cr.setSourceRGBA(color.r, color.g, color.b, opacity);
                cr.arc(cx, cy, radius, 0, Math.PI * 2);
                cr.setLineWidth(this._lineThickness * this._scale);
                cr.stroke();
            }
        }

        // Pulsing center dot
        const pulse = (Math.sin(this._time * 3 * this._animationSpeed * 2.5) + 1) / 2;
        const centerRadius = (this._centerSize + pulse * 2) * this._scale;
        const centerOpacity = (0.7 + pulse * 0.3) * this._opacityMultiplier * alpha;

        cr.setSourceRGBA(color.r, color.g, color.b, centerOpacity);
        cr.arc(cx, cy, centerRadius, 0, Math.PI * 2);
        cr.fill();
    }

    _drawProcessing(cr, cx, cy, alpha) {
        const color = STATE_COLORS.processing;

        // 5 radiating wave rings expanding outward
        for (let i = 0; i < this._ringCount; i++) {
            const t = (this._time * this._animationSpeed * 5 + i * this._ringSpacing) % (Math.PI * 2);
            const radius = (10 + t * 6.4) * this._scale;
            const opacity = (1 - t / (Math.PI * 2)) * 0.4 * this._opacityMultiplier * alpha;

            cr.setSourceRGBA(color.r, color.g, color.b, opacity);
            cr.arc(cx, cy, radius, 0, Math.PI * 2);
            cr.setLineWidth(this._lineThickness * this._scale);
            cr.stroke();
        }

        // Static center dot (slightly lighter blue)
        const centerOpacity = 0.6 * this._opacityMultiplier * alpha;
        cr.setSourceRGBA(0.471, 0.706, 1.0, centerOpacity);
        cr.arc(cx, cy, this._centerSize * this._scale, 0, Math.PI * 2);
        cr.fill();
    }

    _drawSuccess(cr, cx, cy, alpha) {
        const color = STATE_COLORS.success;
        const isTransitioningIn = this._state === 'success' && this._transitionProgress < 1;
        const scale = isTransitioningIn ? Math.min(this._transitionProgress * 1.5, 1) : 1;
        const overshoot = isTransitioningIn ? this._outBackEasing(this._transitionProgress) : 1;

        // Success ring
        cr.setSourceRGBA(color.r, color.g, color.b, 0.3 * scale * alpha);
        cr.arc(cx, cy, 50 * this._scale, 0, Math.PI * 2);
        cr.setLineWidth(2 * this._scale);
        cr.stroke();

        // Checkmark with overshoot animation
        cr.save();
        cr.translate(cx, cy);
        cr.scale(overshoot * this._scale, overshoot * this._scale);

        cr.setSourceRGBA(0.235, 0.863, 0.510, 0.8 * scale * alpha);
        cr.setLineWidth(3);
        cr.setLineCap(1);  // CAIRO_LINE_CAP_ROUND
        cr.setLineJoin(1); // CAIRO_LINE_JOIN_ROUND

        cr.moveTo(-15, 0);
        cr.lineTo(-5, 10);
        cr.lineTo(15, -10);
        cr.stroke();

        cr.restore();

        // Subtle pulse ring when fully transitioned
        if (scale >= 1) {
            const pulse = (Math.sin(this._time * 2) + 1) / 2;
            const pulseOpacity = 0.15 * (1 - pulse * 0.5) * alpha;
            cr.setSourceRGBA(color.r, color.g, color.b, pulseOpacity);
            cr.arc(cx, cy, (60 + pulse * 5) * this._scale, 0, Math.PI * 2);
            cr.setLineWidth(1 * this._scale);
            cr.stroke();
        }
    }

    _drawFailure(cr, cx, cy, alpha) {
        const color = STATE_COLORS.failure;
        const isTransitioningIn = this._state === 'failure' && this._transitionProgress < 1;
        const scale = isTransitioningIn ? Math.min(this._transitionProgress * 1.5, 1) : 1;

        // Shake effect during transition
        let shake = 0;
        if (isTransitioningIn && this._transitionProgress < 0.3) {
            shake = Math.sin(this._transitionProgress * 50) * 3 *
                    (1 - this._transitionProgress / 0.3) * this._scale;
        }

        // Error ring
        cr.setSourceRGBA(color.r, color.g, color.b, 0.3 * scale * alpha);
        cr.arc(cx + shake, cy, 50 * this._scale, 0, Math.PI * 2);
        cr.setLineWidth(2 * this._scale);
        cr.stroke();

        // X mark
        cr.save();
        cr.translate(cx + shake, cy);
        cr.scale(scale * this._scale, scale * this._scale);

        cr.setSourceRGBA(1.0, 0.471, 0.471, 0.8 * scale * alpha);
        cr.setLineWidth(3);
        cr.setLineCap(1);  // CAIRO_LINE_CAP_ROUND

        cr.moveTo(-12, -12);
        cr.lineTo(12, 12);
        cr.moveTo(12, -12);
        cr.lineTo(-12, 12);
        cr.stroke();

        cr.restore();

        // Breaking wave / particle effect
        if (isTransitioningIn) {
            const numFragments = 8;
            for (let i = 0; i < numFragments; i++) {
                const angle = (i / numFragments) * Math.PI * 2;
                const distance = this._transitionProgress * 30 * this._scale;
                const x = cx + Math.cos(angle) * distance;
                const y = cy + Math.sin(angle) * distance;
                const opacity = 0.3 * (1 - this._transitionProgress) * alpha;

                cr.setSourceRGBA(color.r, color.g, color.b, opacity);
                cr.arc(x, y, 2 * this._scale, 0, Math.PI * 2);
                cr.fill();
            }
        }
    }

    destroy() {
        this._stopAnimationLoop();

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
