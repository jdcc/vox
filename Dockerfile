# Vox server with GPU support
FROM nvidia/cuda:12.1-runtime-ubuntu22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY config/ config/
COPY src/ src/

# Install dependencies
RUN uv sync --no-dev

# Expose WebSocket port
EXPOSE 9876

# Create cache directory for models
RUN mkdir -p /root/.cache/vox/models

# Run the server
CMD ["uv", "run", "vox", "server", "--host", "0.0.0.0"]
