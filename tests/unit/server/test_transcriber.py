"""Tests for vox.server.transcriber module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vox.config import Config
from vox.server.transcriber import Transcriber, TranscriptionResult


class TestTranscriptionResult:
    """Tests for TranscriptionResult dataclass."""

    def test_create_result(self):
        result = TranscriptionResult(text="Hello", language="en", duration=1.5)
        assert result.text == "Hello"
        assert result.language == "en"
        assert result.duration == 1.5

    def test_default_values(self):
        result = TranscriptionResult(text="Hello")
        assert result.text == "Hello"
        assert result.language == "en"
        assert result.duration == 0.0


class TestTranscriber:
    """Tests for Transcriber class."""

    def test_init_no_model(self):
        transcriber = Transcriber()
        assert transcriber.model is None
        assert transcriber.current_model_id is None
        assert transcriber.device == "auto"
        assert transcriber.compute_type == "int8"

    def test_init_with_model_id(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en", device="cpu")
            assert transcriber.device == "cpu"
            assert transcriber.current_model_id == "small.en"
            mock_manager.ensure_model.assert_called_once_with("small.en")

    def test_init_custom_device_and_compute_type(self):
        transcriber = Transcriber(device="cuda", compute_type="float16")
        assert transcriber.device == "cuda"
        assert transcriber.compute_type == "float16"

    def test_resolve_device_cpu(self):
        transcriber = Transcriber(device="cpu")
        assert transcriber._resolve_device() == "cpu"

    def test_resolve_device_cuda(self):
        transcriber = Transcriber(device="cuda")
        assert transcriber._resolve_device() == "cuda"

    def test_resolve_device_auto_no_torch(self):
        transcriber = Transcriber(device="auto")
        with patch.dict("sys.modules", {"torch": None}):
            assert transcriber._resolve_device() == "cpu"

    def test_resolve_device_auto_with_cuda(self):
        transcriber = Transcriber(device="auto")
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert transcriber._resolve_device() == "cuda"

    def test_resolve_device_auto_without_cuda(self):
        transcriber = Transcriber(device="auto")
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert transcriber._resolve_device() == "cpu"

    def test_load_model(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber()
            transcriber.load_model("small.en")

            assert transcriber.current_model_id == "small.en"
            assert transcriber.model is not None
            mock_manager.ensure_model.assert_called_once_with("small.en")

    def test_load_model_already_loaded(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en")
            initial_model = transcriber.model

            # Load same model again
            transcriber.load_model("small.en")

            # Model should not be reloaded
            assert transcriber.model is initial_model
            assert mock_manager.ensure_model.call_count == 1

    def test_load_model_different_model(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en")

            # Load different model
            transcriber.load_model("tiny.en")

            assert transcriber.current_model_id == "tiny.en"
            assert mock_manager.ensure_model.call_count == 2

    def test_transcribe_no_model_loaded(self):
        transcriber = Transcriber()
        audio = np.zeros(16000, dtype=np.float32)

        with pytest.raises(RuntimeError, match="No model loaded"):
            transcriber.transcribe(audio)

    def test_transcribe_with_numpy_array(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en")
            audio = np.zeros(16000, dtype=np.float32)

            result = transcriber.transcribe(audio)

            assert isinstance(result, TranscriptionResult)
            assert result.text == "Hello, world!"
            assert result.language == "en"
            assert result.duration == 1.5

    def test_transcribe_with_path(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en")
            audio_path = Path("/tmp/audio.wav")

            result = transcriber.transcribe(audio_path)

            assert isinstance(result, TranscriptionResult)
            assert result.text == "Hello, world!"

    def test_transcribe_with_string_path(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en")

            result = transcriber.transcribe("/tmp/audio.wav")

            assert isinstance(result, TranscriptionResult)
            assert result.text == "Hello, world!"

    def test_transcribe_multiple_segments(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            # Mock multiple segments
            mock_segment1 = MagicMock()
            mock_segment1.text = " Hello "
            mock_segment2 = MagicMock()
            mock_segment2.text = " world "

            mock_info = MagicMock()
            mock_info.language = "en"
            mock_info.duration = 2.0

            mock_whisper_model.transcribe.return_value = (
                iter([mock_segment1, mock_segment2]),
                mock_info,
            )

            transcriber = Transcriber(model_id="small.en")
            audio = np.zeros(16000, dtype=np.float32)

            result = transcriber.transcribe(audio)

            assert result.text == "Hello world"

    def test_transcribe_bytes(self, mock_whisper_model, sample_audio_bytes):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en")

            result = transcriber.transcribe_bytes(sample_audio_bytes)

            assert isinstance(result, TranscriptionResult)
            assert result.text == "Hello, world!"

    def test_transcribe_bytes_custom_sample_rate(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber(model_id="small.en")

            # Create 1 second of audio at 48kHz
            audio = (np.zeros(48000, dtype=np.float32) * 32768).astype(np.int16)
            audio_bytes = audio.tobytes()

            result = transcriber.transcribe_bytes(audio_bytes, sample_rate=48000)

            assert isinstance(result, TranscriptionResult)

    def test_from_config(self, sample_config, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            transcriber = Transcriber.from_config(sample_config)

            assert transcriber.current_model_id == sample_config.model.default
            assert transcriber.device == sample_config.model.device
            assert transcriber.compute_type == sample_config.model.compute_type

    def test_transcribe_empty_audio(self, mock_whisper_model):
        with patch("vox.server.transcriber.ModelManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ensure_model.return_value = Path("/tmp/model")
            mock_manager_class.return_value = mock_manager

            # Mock empty transcription
            mock_info = MagicMock()
            mock_info.language = "en"
            mock_info.duration = 0.0

            mock_whisper_model.transcribe.return_value = (iter([]), mock_info)

            transcriber = Transcriber(model_id="small.en")
            audio = np.zeros(100, dtype=np.float32)

            result = transcriber.transcribe(audio)

            assert result.text == ""
            assert result.duration == 0.0
