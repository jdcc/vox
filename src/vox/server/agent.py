"""Agent keyword parsing and LLM integration."""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator

import litellm

from vox.config import Config

logger = logging.getLogger(__name__)


class AgentMode(Enum):
    """Processing mode based on keyword detection."""

    PASSTHROUGH = "passthrough"
    TRANSFORM = "transform"
    GENERATE = "generate"


@dataclass
class ParsedText:
    """Result of parsing text for agent keywords."""

    mode: AgentMode
    original_text: str
    context: str
    instruction: str


class AgentProcessor:
    """Processes text with optional LLM transformation."""

    KEYWORD_PATTERN = re.compile(
        r"^(.*?)\s*\bAgent\b[,:\s]+(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, config: Config) -> None:
        """Initialize the agent processor.

        Args:
            config: Application configuration
        """
        self.config = config
        self.enabled = config.agent.enabled
        self.keyword = config.agent.keyword

        llm_config = config.agent.llm
        self.provider = llm_config.provider
        self.model = llm_config.model
        self.api_key = llm_config.get_api_key()

        if self.api_key:
            if self.provider == "anthropic":
                litellm.anthropic_key = self.api_key
            elif self.provider == "openai":
                litellm.openai_key = self.api_key

    def parse(self, text: str) -> ParsedText:
        """Parse text for agent keywords.

        Args:
            text: The transcribed text

        Returns:
            ParsedText with mode and components
        """
        if not self.enabled:
            return ParsedText(
                mode=AgentMode.PASSTHROUGH,
                original_text=text,
                context="",
                instruction="",
            )

        match = self.KEYWORD_PATTERN.match(text)

        if not match:
            return ParsedText(
                mode=AgentMode.PASSTHROUGH,
                original_text=text,
                context="",
                instruction="",
            )

        context = match.group(1).strip()
        instruction = match.group(2).strip()

        if not context:
            return ParsedText(
                mode=AgentMode.GENERATE,
                original_text=text,
                context="",
                instruction=instruction,
            )

        return ParsedText(
            mode=AgentMode.TRANSFORM,
            original_text=text,
            context=context,
            instruction=instruction,
        )

    async def process(self, text: str) -> str:
        """Process text, applying LLM transformation if needed.

        Args:
            text: The transcribed text

        Returns:
            Processed text (original or LLM-transformed)
        """
        parsed = self.parse(text)

        if parsed.mode == AgentMode.PASSTHROUGH:
            return parsed.original_text

        if parsed.mode == AgentMode.GENERATE:
            return await self._generate(parsed.instruction)

        return await self._transform(parsed.context, parsed.instruction)

    async def _get_llm_response(self, messages: list[dict]) -> str:
        """Get response from LLM.

        Args:
            messages: List of message dicts

        Returns:
            LLM response text
        """
        model_name = f"{self.provider}/{self.model}"

        response = await litellm.acompletion(
            model=model_name,
            messages=messages,
            max_tokens=2000,
        )

        return response.choices[0].message.content

    async def _transform(self, context: str, instruction: str) -> str:
        """Transform text using LLM.

        Args:
            context: The original text to transform
            instruction: How to transform it

        Returns:
            Transformed text
        """
        logger.info(f"Transforming text: '{context}' with instruction: '{instruction}'")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that transforms text based on instructions. "
                    "Output only the transformed text, nothing else. No explanations, no quotes, "
                    "no prefixes like 'Here is' - just the transformed text itself."
                ),
            },
            {
                "role": "user",
                "content": f"Transform this text: \"{context}\"\n\nInstruction: {instruction}",
            },
        ]

        return await self._get_llm_response(messages)

    async def _generate(self, instruction: str) -> str:
        """Generate text using LLM.

        Args:
            instruction: What to generate

        Returns:
            Generated text
        """
        logger.info(f"Generating text for: '{instruction}'")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Generate text based on the user's request. "
                    "Output only the requested content, nothing else. No explanations, no quotes, "
                    "no prefixes like 'Here is' - just the content itself."
                ),
            },
            {
                "role": "user",
                "content": instruction,
            },
        ]

        return await self._get_llm_response(messages)

    async def process_stream(self, text: str) -> AsyncIterator[str]:
        """Process text with streaming LLM response.

        Args:
            text: The transcribed text

        Yields:
            Text chunks as they're generated
        """
        parsed = self.parse(text)

        if parsed.mode == AgentMode.PASSTHROUGH:
            yield parsed.original_text
            return

        if parsed.mode == AgentMode.GENERATE:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. Generate text based on the user's request. "
                        "Output only the requested content, nothing else."
                    ),
                },
                {"role": "user", "content": parsed.instruction},
            ]
        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant that transforms text based on instructions. "
                        "Output only the transformed text, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Transform this text: \"{parsed.context}\"\n\nInstruction: {parsed.instruction}",
                },
            ]

        model_name = f"{self.provider}/{self.model}"

        response = await litellm.acompletion(
            model=model_name,
            messages=messages,
            max_tokens=2000,
            stream=True,
        )

        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
