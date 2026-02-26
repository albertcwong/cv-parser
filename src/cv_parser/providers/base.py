"""Provider protocol and factory."""

import os
from collections.abc import Callable
from typing import Protocol

from cv_parser.schemas import CVParseResult, Usage


class Provider(Protocol):
    """Protocol for LLM provider adapters."""

    def parse(
        self,
        document: bytes,
        mime_type: str,
        *,
        previous_result: CVParseResult | None = None,
        user_feedback: str | None = None,
        retry_on_validation_error: bool = True,
        max_retries: int = 1,
        stream_callback: Callable[[str], None] | None = None,
        prompt: str | None = None,
        return_raw: bool = False,
    ) -> tuple[CVParseResult | str, Usage | None]:
        """Parse document. When return_raw=True, returns (raw_text, usage) instead of (CVParseResult, usage)."""
        ...


def get_provider(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> Provider:
    """Get provider from env or args. CLI overrides env."""
    p = provider or os.environ.get("CV_PARSER_PROVIDER", "openai")
    m = model or os.environ.get("CV_PARSER_MODEL")
    key = api_key or _api_key_for(p)

    if p == "openai":
        from cv_parser.providers.openai import OpenAIProvider
        return OpenAIProvider(model=m, api_key=key)
    if p == "anthropic":
        from cv_parser.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=m, api_key=key)
    if p == "gemini":
        from cv_parser.providers.gemini import GeminiProvider
        return GeminiProvider(model=m, api_key=key)
    raise ValueError(f"Unknown provider: {p}. Use openai, anthropic, or gemini.")


def _api_key_for(provider: str) -> str | None:
    keys = {
        "openai": ["OPENAI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    }
    for env in keys.get(provider, []):
        v = os.environ.get(env)
        if v:
            return v
    return None
