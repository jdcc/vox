# Vox

Lightweight speech-to-text with LLM agent integration.

## Features

- **Fast transcription** using faster-whisper (CTranslate2-optimized)
- **Hold-to-record** with global hotkeys via evdev
- **LLM agent integration** for text transformation and generation
- **Client-server architecture** for remote GPU support
- **System tray icon** with visual state indicators
- **TUI** for model management and settings

## Quick Start

```bash
# Install dependencies
make install
make install-deps

# Add yourself to input group (for hotkeys)
make add-input-group
# Log out and back in

# Create config
make config-init

# Download a model
make models-download

# Start server
make server

# In another terminal, start client
make client
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

- Ubuntu + Wayland
- Python 3.11+
- System packages: `wl-clipboard`, `wtype`, `libportaudio2`
- User must be in `input` group for hotkeys

## Docker (Server)

```bash
make build      # Build image
make run        # Run with GPU
make run-cpu    # Run without GPU
make logs       # View logs
make stop       # Stop container
```
