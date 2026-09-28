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


def _local_config(**llm_overrides) -> Config:
    llm = {"provider": "openai", "model": "gemma-4-e2b", "api_base": "http://127.0.0.1:8090/v1"}
    llm.update(llm_overrides)
    return Config(agent=AgentConfig(user_name="Justin", llm=LLMConfig(**llm)))


@pytest.mark.asyncio
async def test_api_base_is_passed_with_placeholder_key(mock_litellm) -> None:
    processor = AgentProcessor(_local_config())

    await processor.process("Agent, write a haiku")

    kwargs = mock_litellm.acompletion.call_args.kwargs
    assert kwargs["model"] == "openai/gemma-4-e2b"
    assert kwargs["api_base"] == "http://127.0.0.1:8090/v1"
    assert kwargs["api_key"] == "local"


@pytest.mark.asyncio
async def test_api_base_uses_configured_key(mock_litellm) -> None:
    processor = AgentProcessor(_local_config(api_key="sk-local"))

    await processor.process("Agent, write a haiku")

    assert mock_litellm.acompletion.call_args.kwargs["api_key"] == "sk-local"


@pytest.mark.asyncio
async def test_no_api_base_leaves_endpoint_to_provider(mock_litellm) -> None:
    processor = AgentProcessor(Config())

    await processor.process("Agent, write a haiku")

    kwargs = mock_litellm.acompletion.call_args.kwargs
    assert "api_base" not in kwargs
    assert "api_key" not in kwargs


@pytest.mark.asyncio
async def test_transform_messages(mock_litellm) -> None:
    processor = AgentProcessor(_local_config())

    await processor.process("See you Friday. Agent, make it formal")

    system, user = mock_litellm.acompletion.call_args.kwargs["messages"]
    assert system == {"role": "system", "content": processor.transform_prompt}
    assert user["content"] == 'Text: "See you Friday."\n\nInstruction: make it formal'


@pytest.mark.asyncio
async def test_generate_messages(mock_litellm) -> None:
    processor = AgentProcessor(_local_config())

    await processor.process("Agent, write a haiku")

    system, user = mock_litellm.acompletion.call_args.kwargs["messages"]
    assert system == {"role": "system", "content": processor.generate_prompt}
    assert user == {"role": "user", "content": "write a haiku"}


def test_user_name_adds_sign_off() -> None:
    processor = AgentProcessor(_local_config())

    for prompt in (processor.transform_prompt, processor.generate_prompt):
        assert "if an email needs a sign-off, sign it Justin" in prompt


def test_no_user_name_omits_sign_off() -> None:
    processor = AgentProcessor(Config())

    for prompt in (processor.transform_prompt, processor.generate_prompt):
        assert "sign-off" not in prompt
        assert "{sign_off}" not in prompt


@pytest.mark.asyncio
async def test_warm_up_primes_both_system_prompts(mock_litellm) -> None:
    processor = AgentProcessor(_local_config())

    await processor.warm_up()

    calls = mock_litellm.acompletion.call_args_list
    assert [c.kwargs["messages"][0]["content"] for c in calls] == [
        processor.transform_prompt,
        processor.generate_prompt,
    ]
    assert all(c.kwargs["max_tokens"] == 1 for c in calls)


@pytest.mark.asyncio
async def test_warm_up_skipped_without_local_server(mock_litellm) -> None:
    await AgentProcessor(Config()).warm_up()

    mock_litellm.acompletion.assert_not_called()


@pytest.mark.asyncio
async def test_warm_up_skipped_when_disabled(mock_litellm) -> None:
    config = _local_config()
    config.agent.enabled = False

    await AgentProcessor(config).warm_up()

    mock_litellm.acompletion.assert_not_called()


@pytest.mark.asyncio
async def test_warm_up_failure_is_not_raised(mock_litellm) -> None:
    mock_litellm.acompletion.side_effect = ConnectionError("server down")
    processor = AgentProcessor(_local_config())

    await processor.warm_up(attempts=3, delay=0)

    assert mock_litellm.acompletion.call_count == 3


@pytest.mark.asyncio
async def test_warm_up_retries_while_server_loads(mock_litellm) -> None:
    ok = mock_litellm.acompletion.return_value
    mock_litellm.acompletion.side_effect = [ConnectionError("loading"), ok, ok]
    processor = AgentProcessor(_local_config())

    await processor.warm_up(attempts=3, delay=0)

    assert mock_litellm.acompletion.call_count == 3
