"""Faster-whisper transcription wrapper."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from faster_whisper import WhisperModel

from vox.config import Config
from vox.server.model_manager import ModelManager

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of a transcription."""

    text: str
    language: str = "en"
    duration: float = 0.0


class Transcriber:
    """Wrapper for faster-whisper transcription."""

    def __init__(
        self,
        model_id: str | None = None,
        device: Literal["auto", "cpu", "cuda"] = "auto",
        compute_type: str = "int8",
    ) -> None:
        """Initialize the transcriber.

        Args:
            model_id: Model to load (e.g., "small.en"). If None, uses config default.
            device: Device to run on (auto, cpu, cuda)
            compute_type: Compute type for quantization
        """
        self.model_manager = ModelManager()
        self.model: WhisperModel | None = None
        self.current_model_id: str | None = None
        self.device = device
        self.compute_type = compute_type

        if model_id:
            self.load_model(model_id)

    def _resolve_device(self) -> str:
        """Resolve 'auto' device to actual device."""
        if self.device != "auto":
            return self.device

        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass

        return "cpu"

    def load_model(self, model_id: str) -> None:
        """Load a whisper model.

        Args:
            model_id: The model ID to load
        """
        if self.current_model_id == model_id and self.model is not None:
            logger.info(f"Model {model_id} already loaded")
            return

        logger.info(f"Loading model {model_id}...")

        model_path = self.model_manager.ensure_model(model_id)
        device = self._resolve_device()

        logger.info(f"Using device: {device}, compute_type: {self.compute_type}")

        self.model = WhisperModel(
            str(model_path),
            device=device,
            compute_type=self.compute_type,
        )
        self.current_model_id = model_id

        logger.info(f"Model {model_id} loaded successfully")

    def transcribe(
        self,
        audio: np.ndarray | Path | str,
        language: str = "en",
    ) -> TranscriptionResult:
        """Transcribe audio to text.

        Args:
            audio: Audio data as numpy array (float32, mono, 16kHz) or path to audio file
            language: Language code (default: "en")

        Returns:
            TranscriptionResult with transcribed text

        Raises:
            RuntimeError: If no model is loaded
        """
        if self.model is None:
            raise RuntimeError("No model loaded. Call load_model() first.")

        if isinstance(audio, (Path, str)):
            audio_input = str(audio)
        else:
            audio_input = audio

        segments, info = self.model.transcribe(
            audio_input,
            language=language,
            beam_size=5,
            vad_filter=True,
        )

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        full_text = " ".join(text_parts)

        return TranscriptionResult(
            text=full_text,
            language=info.language,
            duration=info.duration,
        )

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        """Transcribe raw audio bytes.

        Args:
            audio_bytes: Raw PCM audio bytes (int16, mono)
            sample_rate: Sample rate of the audio

        Returns:
            TranscriptionResult with transcribed text
        """
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio_array.astype(np.float32) / 32768.0

        return self.transcribe(audio_float, language="en")

    @classmethod
    def from_config(cls, config: Config) -> "Transcriber":
        """Create a transcriber from configuration.

        Args:
            config: Application configuration

        Returns:
            Configured Transcriber instance
        """
        return cls(
            model_id=config.model.default,
            device=config.model.device,
            compute_type=config.model.compute_type,
        )
