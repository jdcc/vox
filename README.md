# Vox

Lightweight speech-to-text with LLM agent integration.

## Features

- **Fast transcription** using faster-whisper (CTranslate2-optimized)
- **Hold-to-record** with global hotkeys via GNOME Shell extension
- **LLM agent integration** for text transformation and generation
- **Client-server architecture** for remote GPU support
- **Visual indicator** overlay for recording/processing states
- **TUI** for model management and settings

## Quick Start

```bash
# Full setup (installs deps, extension, config, and model)
make setup

# Enable the GNOME extension
gnome-extensions enable vox@local
# Log out and back in (required on Wayland)

# Start vox
make start
```

## Usage

1. Hold `Ctrl+Space` to record
2. Release to transcribe
3. Text is copied to clipboard and pasted

### Agent Commands

- **Passthrough:** "Hello world" → outputs "Hello world"
- **Transform:** "Thanks, Justin. Agent, make that professional" → LLM transforms the text
- **Generate:** "Agent: Draft a meeting followup email" → LLM generates from scratch

## Configuration

Edit `~/.config/vox/config.yaml`:

```yaml
hotkey:
  trigger: ctrl+space

server:
  host: localhost
  port: 9876

model:
  default: small.en
  device: auto
  compute_type: int8

output:
  method: both
  typing_method: paste

agent:
  enabled: true
  keyword: Agent
  llm:
    provider: anthropic
    model: claude-sonnet-4-20250514
    api_key: ${ANTHROPIC_API_KEY}
```

## System Requirements

- **GNOME Shell** on Wayland (extension required for hotkeys)
- Python 3.11+
- System packages: `wl-clipboard`, `ydotool`, `libportaudio2`

## GNOME Extension

The Vox GNOME Shell extension provides:
- Global hotkey detection with press-and-hold semantics
- Visual indicator overlay (recording/processing/success/failure)
- D-Bus communication with the Python client

```bash
# Install extension
make install-extension

# Enable extension
gnome-extensions enable vox@local

# Restart GNOME Shell (log out/in on Wayland)

# Uninstall extension
make uninstall-extension
```

**Note:** This approach is GNOME-specific and won't work on other desktop environments (KDE, Sway, etc.).

## Docker (Server)

```bash
make build      # Build image
make run        # Run with GPU
make run-cpu    # Run without GPU
make logs       # View logs
make stop       # Stop container
```
