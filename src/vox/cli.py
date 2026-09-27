"""CLI commands for vox."""

import asyncio
import logging
import sys

import click

from vox import __version__
from vox.config import load_config, create_default_config, get_config_path, ModelsDB


def setup_logging(verbose: bool) -> None:
    """Set up logging configuration.

    Args:
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not verbose:
        logging.getLogger("websockets").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


@click.group()
@click.version_option(version=__version__)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Vox - Lightweight speech-to-text with LLM agent integration."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@main.command()
@click.option("--host", "-h", default=None, help="Host to bind to")
@click.option("--port", "-p", default=None, type=int, help="Port to bind to")
@click.pass_context
def server(ctx: click.Context, host: str | None, port: int | None) -> None:
    """Start the vox server."""
    from vox.server.app import run_server

    click.echo("Starting vox server...")
    asyncio.run(run_server(host, port))


@main.command()
@click.pass_context
def client(ctx: click.Context) -> None:
    """Start the vox client."""
    from vox.client.app import run_client

    click.echo("Starting vox client...")
    try:
        asyncio.run(run_client())
    except RuntimeError as e:
        # Exit non-zero so a supervisor (systemd Restart=on-failure) retries
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def tui(ctx: click.Context) -> None:
    """Open the vox TUI."""
    from vox.tui.app import run_tui

    run_tui()


@main.command()
@click.argument("audio_file", type=click.Path(exists=True))
@click.option("--model", "-m", default=None, help="Model to use")
@click.pass_context
def transcribe(ctx: click.Context, audio_file: str, model: str | None) -> None:
    """Transcribe an audio file."""
    from vox.server.transcriber import Transcriber

    config = load_config()
    model_id = model or config.model.default

    click.echo(f"Loading model {model_id}...")

    transcriber = Transcriber(
        model_id=model_id,
        device=config.model.device,
        compute_type=config.model.compute_type,
    )

    click.echo(f"Transcribing {audio_file}...")

    result = transcriber.transcribe(audio_file)

    click.echo(f"\nTranscription ({result.duration:.1f}s):")
    click.echo(result.text)


@main.group()
def models() -> None:
    """Manage whisper models."""
    pass


@models.command("list")
def models_list() -> None:
    """List available models."""
    db = ModelsDB()
    models = db.list_models()

    click.echo("Available models:")
    click.echo()

    for model in models:
        status = "Downloaded" if model.is_downloaded() else "Not downloaded"
        click.echo(f"  {model.id:<12} {model.size:<8} {status}")


@models.command("download")
@click.argument("model_id")
def models_download(model_id: str) -> None:
    """Download a model."""
    from vox.server.model_manager import ModelManager

    manager = ModelManager()

    model = manager.models_db.get_model(model_id)
    if not model:
        click.echo(f"Unknown model: {model_id}", err=True)
        click.echo("Use 'vox models list' to see available models.", err=True)
        sys.exit(1)

    if model.is_downloaded():
        click.echo(f"Model {model_id} is already downloaded.")
        return

    click.echo(f"Downloading {model.name} ({model.size})...")

    def progress(msg: str) -> None:
        click.echo(msg)

    manager.download_model(model_id, progress_callback=progress)
    click.echo("Done!")


@models.command("delete")
@click.argument("model_id")
@click.confirmation_option(prompt="Are you sure you want to delete this model?")
def models_delete(model_id: str) -> None:
    """Delete a downloaded model."""
    from vox.server.model_manager import ModelManager

    manager = ModelManager()

    if manager.delete_model(model_id):
        click.echo(f"Deleted model {model_id}")
    else:
        click.echo(f"Model {model_id} not found or not downloaded.", err=True)


@main.group()
def config() -> None:
    """Manage configuration."""
    pass


@config.command("show")
def config_show() -> None:
    """Show current configuration."""
    import yaml

    config = load_config()
    click.echo(yaml.dump(config.model_dump(), default_flow_style=False))


@config.command("path")
def config_path() -> None:
    """Show configuration file path."""
    click.echo(get_config_path())


@config.command("init")
def config_init() -> None:
    """Create default configuration file."""
    config_path = get_config_path()

    if config_path.exists():
        click.echo(f"Configuration file already exists: {config_path}")
        if not click.confirm("Overwrite?"):
            return

    create_default_config()
    click.echo(f"Created configuration file: {config_path}")


@main.command()
def check() -> None:
    """Check system dependencies and permissions."""
    from vox.client.output import check_wayland_tools

    click.echo("Checking system dependencies...")
    click.echo()

    click.echo("Wayland tools:")
    tools = check_wayland_tools()
    for tool, available in tools.items():
        status = click.style("OK", fg="green") if available else click.style("MISSING", fg="red")
        click.echo(f"  {tool}: {status}")

    if not all(tools.values()):
        click.echo()
        click.echo("Install missing tools with:")
        click.echo("  sudo apt install wl-clipboard")

    click.echo()
    click.echo("Configuration:")
    config_file = get_config_path()
    if config_file.exists():
        click.echo(f"  Config file: {click.style('OK', fg='green')} ({config_file})")
    else:
        click.echo(f"  Config file: {click.style('NOT FOUND', fg='yellow')}")
        click.echo("  Run 'vox config init' to create default configuration.")


if __name__ == "__main__":
    main()
