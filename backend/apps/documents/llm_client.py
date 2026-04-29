import time
import logging
from typing import Any
from django.conf import settings
import anthropic

logger = logging.getLogger(__name__)


class LLMClient:
    """Единая точка входа для всех вызовов Claude API."""

    MODEL = "claude-sonnet-4-6"

    def __init__(self) -> None:
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
    ) -> str:
        start = time.monotonic()
        messages = [{"role": "user", "content": prompt}]

        response = self.client.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=system or anthropic.NOT_GIVEN,
            messages=messages,
        )

        elapsed = time.monotonic() - start
        usage = response.usage
        logger.info(
            "LLM call model=%s input_tokens=%d output_tokens=%d elapsed=%.2fs",
            self.MODEL,
            usage.input_tokens,
            usage.output_tokens,
            elapsed,
        )
        return response.content[0].text


llm = LLMClient()
