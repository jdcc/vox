.PHONY: build run stop logs client server tui check install clean setup setup-full start start-bg

# =============================================================================
# Quick Start (from clean machine)
# =============================================================================

# Full setup: system deps + python deps + config + model download
# Note: Does NOT add to input group (requires logout). Run 'make setup-full' for that.
setup: install-deps install config-init models-download
	@echo ""
	@echo "=========================================="
	@echo "Setup complete!"
	@echo "=========================================="
	@echo ""
	@echo "Next steps:"
	@echo "  1. Add yourself to input group (for hotkeys):"
	@echo "     make add-input-group"
	@echo "     Then log out and back in"
	@echo ""
	@echo "  2. Start vox:"
	@echo "     make start"
	@echo ""

# Full setup including input group (will require logout/login after)
setup-full: install-deps install config-init models-download add-input-group
	@echo ""
	@echo "=========================================="
	@echo "Setup complete!"
	@echo "=========================================="
	@echo ""
	@echo "IMPORTANT: Log out and back in for input group to take effect"
	@echo ""
	@echo "Then run: make start"
	@echo ""

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

# Setup commands
install:
	uv venv --python /usr/bin/python3 --system-site-packages --allow-existing
	uv sync

install-deps:
	sudo apt install -y wl-clipboard ydotool libportaudio2 \
		python3-gi gir1.2-ayatanaappindicator3-0.1
	@echo ""
	@echo "Setting up uinput permissions for ydotool..."
	@echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/80-uinput.rules > /dev/null
	sudo udevadm control --reload-rules
	sudo udevadm trigger
	@echo ""
	@echo "Done! You may need to log out/in for uinput group access."

add-input-group:
	sudo usermod -aG input $$USER
	@echo "Please log out and back in for group changes to take effect"

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
	@echo "  make add-input-group  (then log out/in)"
	@echo "  make start      - Run server + client"
	@echo ""
	@echo "Quick start commands:"
	@echo "  make setup      - Full setup (deps + config + model)"
	@echo "  make setup-full - Setup + add to input group"
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
	@echo ""
	@echo "Setup (individual steps):"
	@echo "  make install    - Install Python dependencies"
	@echo "  make install-deps - Install system dependencies (apt)"
	@echo "  make add-input-group - Add user to input group"
	@echo "  make config-init - Create default config file"
	@echo ""
	@echo "Models:"
	@echo "  make models-list     - List available models"
	@echo "  make models-download - Download default model (small.en)"
