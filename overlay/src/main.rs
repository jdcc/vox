//! vox-overlay: Visual indicator for vox speech-to-text
//!
//! A small GTK4 overlay that shows recording/processing status.
//! Controlled via stdin commands: recording, processing, success, failure, hide

use clap::Parser;
use gtk4::gdk::RGBA;
use gtk4::glib::{self, ControlFlow};
use gtk4::prelude::*;
use gtk4::{Application, ApplicationWindow, DrawingArea};
use gtk4_layer_shell::{Edge, Layer, LayerShell};
use std::cell::{Cell, RefCell};
use std::io::{self, BufRead};
use std::rc::Rc;
use std::sync::mpsc;
use std::thread;

#[derive(Parser)]
#[command(name = "vox-overlay")]
#[command(about = "Visual overlay indicator for vox speech-to-text")]
struct Args {
    /// Position on screen
    #[arg(long, default_value = "top-right")]
    position: String,
}

#[derive(Clone, Copy, PartialEq, Debug)]
enum State {
    Hidden,
    Recording,
    Processing,
    Success,
    Failure,
}

impl State {
    fn from_str(s: &str) -> Option<Self> {
        match s.trim() {
            "hide" => Some(State::Hidden),
            "recording" => Some(State::Recording),
            "processing" => Some(State::Processing),
            "success" => Some(State::Success),
            "failure" => Some(State::Failure),
            _ => None,
        }
    }

    fn color(&self) -> RGBA {
        match self {
            State::Hidden => RGBA::new(0.0, 0.0, 0.0, 0.0),
            State::Recording => RGBA::new(0.96, 0.26, 0.21, 0.9), // Red
            State::Processing => RGBA::new(1.0, 0.76, 0.03, 0.9), // Yellow/amber
            State::Success => RGBA::new(0.30, 0.69, 0.31, 0.9),   // Green
            State::Failure => RGBA::new(0.96, 0.26, 0.21, 0.9),   // Red
        }
    }
}

const SIZE: i32 = 48;
const MARGIN: i32 = 16;

fn main() {
    let args = Args::parse();

    let app = Application::builder()
        .application_id("com.vox.overlay")
        .build();

    let position = args.position.clone();

    app.connect_activate(move |app| {
        build_ui(app, &position);
    });

    app.run_with_args::<&str>(&[]);
}

fn build_ui(app: &Application, position: &str) {
    let window = ApplicationWindow::builder()
        .application(app)
        .default_width(SIZE)
        .default_height(SIZE)
        .decorated(false)
        .resizable(false)
        .build();

    // Set up layer shell
    window.init_layer_shell();
    window.set_layer(Layer::Overlay);
    window.set_keyboard_mode(gtk4_layer_shell::KeyboardMode::None);

    // Set anchor based on position
    match position {
        "top-center" => {
            window.set_anchor(Edge::Top, true);
            window.set_margin(Edge::Top, MARGIN);
        }
        "bottom-right" => {
            window.set_anchor(Edge::Bottom, true);
            window.set_anchor(Edge::Right, true);
            window.set_margin(Edge::Bottom, MARGIN);
            window.set_margin(Edge::Right, MARGIN);
        }
        _ => {
            // top-right (default)
            window.set_anchor(Edge::Top, true);
            window.set_anchor(Edge::Right, true);
            window.set_margin(Edge::Top, MARGIN);
            window.set_margin(Edge::Right, MARGIN);
        }
    }

    // State management
    let state = Rc::new(Cell::new(State::Hidden));
    let animation_phase = Rc::new(Cell::new(0.0f64));
    let flash_timer = Rc::new(Cell::new(0u32));

    // Drawing area
    let drawing_area = DrawingArea::new();
    drawing_area.set_size_request(SIZE, SIZE);

    let state_draw = state.clone();
    let phase_draw = animation_phase.clone();
    drawing_area.set_draw_func(move |_, cr, width, height| {
        let current_state = state_draw.get();
        let phase = phase_draw.get();

        // Clear background (transparent)
        cr.set_operator(gtk4::cairo::Operator::Source);
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.0);
        let _ = cr.paint();

        if current_state == State::Hidden {
            return;
        }

        let color = current_state.color();
        let cx = width as f64 / 2.0;
        let cy = height as f64 / 2.0;
        let base_radius = (width.min(height) as f64 / 2.0) - 4.0;

        match current_state {
            State::Recording => {
                // Pulsing red dot
                let pulse = 0.85 + 0.15 * (phase * std::f64::consts::PI * 2.0).sin();
                let radius = base_radius * pulse;

                cr.set_operator(gtk4::cairo::Operator::Over);
                cr.arc(cx, cy, radius, 0.0, std::f64::consts::PI * 2.0);
                cr.set_source_rgba(
                    color.red() as f64,
                    color.green() as f64,
                    color.blue() as f64,
                    color.alpha() as f64,
                );
                let _ = cr.fill();
            }
            State::Processing => {
                // Yellow spinner
                cr.set_operator(gtk4::cairo::Operator::Over);

                // Background circle
                cr.arc(cx, cy, base_radius, 0.0, std::f64::consts::PI * 2.0);
                cr.set_source_rgba(
                    color.red() as f64,
                    color.green() as f64,
                    color.blue() as f64,
                    0.3,
                );
                let _ = cr.fill();

                // Spinning arc
                let start_angle = phase * std::f64::consts::PI * 2.0;
                let end_angle = start_angle + std::f64::consts::PI * 1.5;
                cr.set_line_width(4.0);
                cr.arc(cx, cy, base_radius - 2.0, start_angle, end_angle);
                cr.set_source_rgba(
                    color.red() as f64,
                    color.green() as f64,
                    color.blue() as f64,
                    color.alpha() as f64,
                );
                let _ = cr.stroke();
            }
            State::Success => {
                // Green circle with checkmark
                cr.set_operator(gtk4::cairo::Operator::Over);
                cr.arc(cx, cy, base_radius, 0.0, std::f64::consts::PI * 2.0);
                cr.set_source_rgba(
                    color.red() as f64,
                    color.green() as f64,
                    color.blue() as f64,
                    color.alpha() as f64,
                );
                let _ = cr.fill();

                // Checkmark
                cr.set_source_rgba(1.0, 1.0, 1.0, 1.0);
                cr.set_line_width(3.0);
                cr.set_line_cap(gtk4::cairo::LineCap::Round);
                cr.move_to(cx - 8.0, cy);
                cr.line_to(cx - 2.0, cy + 6.0);
                cr.line_to(cx + 10.0, cy - 6.0);
                let _ = cr.stroke();
            }
            State::Failure => {
                // Red circle with X
                cr.set_operator(gtk4::cairo::Operator::Over);
                cr.arc(cx, cy, base_radius, 0.0, std::f64::consts::PI * 2.0);
                cr.set_source_rgba(
                    color.red() as f64,
                    color.green() as f64,
                    color.blue() as f64,
                    color.alpha() as f64,
                );
                let _ = cr.fill();

                // X mark
                cr.set_source_rgba(1.0, 1.0, 1.0, 1.0);
                cr.set_line_width(3.0);
                cr.set_line_cap(gtk4::cairo::LineCap::Round);
                cr.move_to(cx - 7.0, cy - 7.0);
                cr.line_to(cx + 7.0, cy + 7.0);
                cr.move_to(cx + 7.0, cy - 7.0);
                cr.line_to(cx - 7.0, cy + 7.0);
                let _ = cr.stroke();
            }
            State::Hidden => {}
        }
    });

    window.set_child(Some(&drawing_area));

    // Stdin reader channel
    let (tx, rx) = mpsc::channel::<State>();

    thread::spawn(move || {
        let stdin = io::stdin();
        for line in stdin.lock().lines() {
            if let Ok(line) = line {
                if let Some(new_state) = State::from_str(&line) {
                    let _ = tx.send(new_state);
                }
            }
        }
    });

    // Animation timer (60 FPS)
    let state_anim = state.clone();
    let phase_anim = animation_phase.clone();
    let flash_anim = flash_timer.clone();
    let drawing_area_anim = drawing_area.clone();
    let window_anim = window.clone();

    glib::timeout_add_local(std::time::Duration::from_millis(16), move || {
        let current = state_anim.get();

        // Update animation phase
        let mut phase = phase_anim.get();
        phase += 0.02;
        if phase > 1.0 {
            phase -= 1.0;
        }
        phase_anim.set(phase);

        // Handle flash states (success/failure auto-hide)
        if current == State::Success || current == State::Failure {
            let timer = flash_anim.get();
            if timer > 60 {
                // ~1 second at 60fps
                state_anim.set(State::Hidden);
                flash_anim.set(0);
                window_anim.set_visible(false);
            } else {
                flash_anim.set(timer + 1);
            }
        }

        // Redraw if visible
        if current != State::Hidden {
            drawing_area_anim.queue_draw();
        }

        ControlFlow::Continue
    });

    // State update from stdin
    let state_rx = state.clone();
    let flash_rx = flash_timer.clone();
    let window_rx = window.clone();
    let drawing_area_rx = drawing_area.clone();

    glib::timeout_add_local(std::time::Duration::from_millis(50), move || {
        while let Ok(new_state) = rx.try_recv() {
            state_rx.set(new_state);

            if new_state == State::Success || new_state == State::Failure {
                flash_rx.set(0);
            }

            if new_state == State::Hidden {
                window_rx.set_visible(false);
            } else {
                window_rx.set_visible(true);
            }

            drawing_area_rx.queue_draw();
        }
        ControlFlow::Continue
    });

    // Start hidden
    window.set_visible(false);
    window.present();
}
