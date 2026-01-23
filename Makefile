.PHONY: build run stop logs client server tui check test install clean setup setup-full start start-bg install-extension uninstall-extension

# =============================================================================
# Quick Start (from clean machine)
# =============================================================================

# Full setup: system deps + python deps + config + model download + extension
setup: install-deps install install-extension config-init models-download
	@echo ""
	@echo "=========================================="
	@echo "Setup complete!"
	@echo "=========================================="
	@echo ""
	@echo "Next steps:"
	@echo "  1. Enable the GNOME extension:"
	@echo "     gnome-extensions enable vox@local"
	@echo "     Then log out and back in (required on Wayland)"
	@echo ""
	@echo "  2. Start vox:"
	@echo "     make start"
	@echo ""

# Full setup (same as setup, extension replaces input group requirement)
setup-full: setup

# Start both server and client (server in background)
start:
	@echo "Starting vox server in background..."
	@uv run vox server &
	@sleep 3
	@echo "Starting vox client..."
	@uv run vox client

# Start server in background, return immediately
start-bg:
	@echo "Starting vox server in background..."
	@nohup uv run vox server > /tmp/vox-server.log 2>&1 &
	@sleep 2
	@echo "Server started. Logs at /tmp/vox-server.log"
	@echo "Run 'make client' to start the client"
	@echo "Run 'make stop-local' to stop the server"

# Stop local server
stop-local:
	@pkill -f "vox server" || echo "No server running"

# =============================================================================
# Docker commands
# =============================================================================
build:
	docker build -t vox-server .

run:
	docker run -d --name vox-server --gpus all -p 9876:9876 \
		-v ~/.cache/vox:/root/.cache/vox vox-server

run-cpu:
	docker run -d --name vox-server -p 9876:9876 \
		-v ~/.cache/vox:/root/.cache/vox vox-server

stop:
	docker stop vox-server && docker rm vox-server

logs:
	docker logs -f vox-server

# Local development commands
client:
	uv run vox client

server:
	uv run vox server

tui:
	uv run vox tui

check:
	uv run vox check

test:
	uv run pytest --cov=src/vox --cov-branch --cov-report=term-missing --cov-fail-under=100

# Setup commands
install:
	uv venv --allow-existing
	uv sync

install-deps:
	sudo apt install -y wl-clipboard libportaudio2

# GNOME Extension commands
install-extension:
	@echo "Installing Vox GNOME Shell extension..."
	@mkdir -p ~/.local/share/gnome-shell/extensions/vox@local/schemas
	@cp extension/metadata.json ~/.local/share/gnome-shell/extensions/vox@local/
	@cp extension/extension.js ~/.local/share/gnome-shell/extensions/vox@local/
	@cp extension/stylesheet.css ~/.local/share/gnome-shell/extensions/vox@local/
	@cp extension/schemas/*.xml ~/.local/share/gnome-shell/extensions/vox@local/schemas/
	@echo "Compiling GSettings schemas..."
	@glib-compile-schemas ~/.local/share/gnome-shell/extensions/vox@local/schemas/
	@echo ""
	@echo "Extension installed to ~/.local/share/gnome-shell/extensions/vox@local/"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Enable the extension:"
	@echo "     gnome-extensions enable vox@local"
	@echo ""
	@echo "  2. Restart GNOME Shell:"
	@echo "     - On Wayland: Log out and back in"
	@echo "     - On X11: Press Alt+F2, type 'r', press Enter"
	@echo ""

uninstall-extension:
	@echo "Uninstalling Vox GNOME Shell extension..."
	@gnome-extensions disable vox@local 2>/dev/null || true
	@rm -rf ~/.local/share/gnome-shell/extensions/vox@local
	@echo "Extension uninstalled."

# Model commands
models-list:
	uv run vox models list

models-download:
	uv run vox models download small.en

# Config commands
config-init:
	uv run vox config init

config-show:
	uv run vox config show

# Clean commands
clean:
	rm -rf .venv __pycache__ src/vox/__pycache__ src/vox/**/__pycache__

clean-models:
	rm -rf ~/.cache/vox/models

# Help
help:
	@echo "Vox - Speech-to-text with LLM agent integration"
	@echo ""
	@echo "QUICK START (clean machine):"
	@echo "  make setup      - Install everything, download model"
	@echo "  gnome-extensions enable vox@local"
	@echo "  (log out/in on Wayland)"
	@echo "  make start      - Run server + client"
	@echo ""
	@echo "Quick start commands:"
	@echo "  make setup      - Full setup (deps + config + model + extension)"
	@echo "  make start      - Start server (bg) + client (fg)"
	@echo "  make start-bg   - Start server in background only"
	@echo "  make stop-local - Stop background server"
	@echo ""
	@echo "Docker commands:"
	@echo "  make build      - Build the server Docker image"
	@echo "  make run        - Run server container with GPU"
	@echo "  make run-cpu    - Run server container without GPU"
	@echo "  make stop       - Stop and remove server container"
	@echo "  make logs       - View server container logs"
	@echo ""
	@echo "Local commands:"
	@echo "  make client     - Run the client locally"
	@echo "  make server     - Run the server locally"
	@echo "  make tui        - Open the TUI"
	@echo "  make check      - Check system dependencies"
	@echo "  make test       - Run tests with coverage"
	@echo ""
	@echo "Setup (individual steps):"
	@echo "  make install    - Install Python dependencies"
	@echo "  make install-deps - Install system dependencies (apt)"
	@echo "  make config-init - Create default config file"
	@echo ""
	@echo "Models:"
	@echo "  make models-list     - List available models"
	@echo "  make models-download - Download default model (small.en)"
	@echo ""
	@echo "GNOME Extension:"
	@echo "  make install-extension   - Install the GNOME Shell extension"
	@echo "  make uninstall-extension - Remove the GNOME Shell extension"
