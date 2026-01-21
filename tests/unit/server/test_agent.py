"""Tests for vox.server.agent."""

import pytest

from vox.config import Config
from vox.config.schema import AgentConfig, LLMConfig
from vox.server.agent import AgentMode, AgentProcessor


def test_parse_disabled() -> None:
    config = Config(agent=AgentConfig(enabled=False))
    processor = AgentProcessor(config)

    parsed = processor.parse("Hello Agent do thing")

    assert parsed.mode == AgentMode.PASSTHROUGH


def test_parse_passthrough_no_keyword() -> None:
    processor = AgentProcessor(Config())

    parsed = processor.parse("Hello world")

    assert parsed.mode == AgentMode.PASSTHROUGH


def test_parse_generate() -> None:
    processor = AgentProcessor(Config())

    parsed = processor.parse("Agent, write a haiku")

    assert parsed.mode == AgentMode.GENERATE
    assert parsed.instruction == "write a haiku"


def test_parse_transform() -> None:
    processor = AgentProcessor(Config())

    parsed = processor.parse("Hello Agent make it formal")

    assert parsed.mode == AgentMode.TRANSFORM
    assert parsed.context == "Hello"
    assert parsed.instruction == "make it formal"


@pytest.mark.asyncio
async def test_process_passthrough() -> None:
    processor = AgentProcessor(Config(agent=AgentConfig(enabled=False)))

    result = await processor.process("plain")

    assert result == "plain"


@pytest.mark.asyncio
async def test_process_generate(mock_litellm) -> None:
    processor = AgentProcessor(Config())

    result = await processor.process("Agent, write a haiku")

    assert result == "Transformed text"


@pytest.mark.asyncio
async def test_process_transform(mock_litellm) -> None:
    processor = AgentProcessor(Config())

    result = await processor.process("Hello Agent make it formal")

    assert result == "Transformed text"


def test_api_key_sets_provider(monkeypatch) -> None:
    import litellm

    config = Config(
        agent=AgentConfig(
            enabled=True,
            llm=LLMConfig(provider="openai", model="gpt-4", api_key="sk-test"),
        )
    )

    processor = AgentProcessor(config)

    assert processor.api_key == "sk-test"
    assert litellm.openai_key == "sk-test"


def test_api_key_sets_anthropic(monkeypatch) -> None:
    import litellm

    config = Config(
        agent=AgentConfig(
            enabled=True,
            llm=LLMConfig(provider="anthropic", model="claude", api_key="sk-test"),
        )
    )

    processor = AgentProcessor(config)

    assert processor.api_key == "sk-test"
    assert litellm.anthropic_key == "sk-test"


def test_api_key_unknown_provider_does_not_set_known_keys(monkeypatch) -> None:
    import litellm

    monkeypatch.setattr(litellm, "openai_key", "original-openai", raising=False)
    monkeypatch.setattr(litellm, "anthropic_key", "original-anthropic", raising=False)

    config = Config(
        agent=AgentConfig(
            enabled=True,
            llm=LLMConfig(provider="custom", model="custom-model", api_key="sk-test"),
        )
    )

    processor = AgentProcessor(config)

    assert processor.api_key == "sk-test"
    assert litellm.openai_key == "original-openai"
    assert litellm.anthropic_key == "original-anthropic"
