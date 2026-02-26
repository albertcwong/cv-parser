"""Anthropic Claude provider adapter."""

import base64
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from cv_parser.prompts import REFINEMENT_PROMPT, SYSTEM_PROMPT, VALIDATION_FIX_PROMPT
from cv_parser.schemas import CVParseResult, Usage

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """Anthropic Claude API provider with PDF/docx support."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self._api_key = api_key

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
        from anthropic import Anthropic

        client = Anthropic(api_key=self._api_key)
        b64 = base64.b64encode(document).decode()

        if prompt is None:
            prompt = SYSTEM_PROMPT
            if previous_result is not None and user_feedback:
                prompt = REFINEMENT_PROMPT.format(
                    feedback=user_feedback,
                    previous=previous_result.model_dump_json(indent=2),
                )

        content: list[dict] = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": b64,
                },
            },
            {"type": "text", "text": prompt},
        ]

        logger.debug("Request: model=%s, doc_size=%d bytes, mime=%s", self.model, len(document), mime_type)

        if stream_callback:
            raw, usage = self._parse_stream(client, content, stream_callback)
        else:
            response = client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": content}],
            )
            raw = ""
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    raw = block.text
                    break
            usage = self._extract_usage(response)

        logger.debug("Raw response (%d chars): %.200s%s", len(raw), raw, "..." if len(raw) > 200 else "")
        if return_raw:
            return raw, usage
        errors: list[str] = []
        for attempt in range(max(0, max_retries) + 1):
            try:
                return self._parse_response(raw), usage
            except Exception as e:
                errors.append(str(e))
                if not retry_on_validation_error or attempt >= max_retries:
                    raise
                try:
                    fixed, _ = self.parse_with_validation_fix(
                        document, mime_type, raw, "\n".join(errors)
                    )
                    return fixed, usage
                except Exception as e2:
                    errors.append(str(e2))

    def _parse_stream(
        self, client: Any, content: list, stream_callback: Callable[[str], None]
    ) -> tuple[str, Usage | None]:
        raw_parts: list[str] = []
        usage: Usage | None = None
        with client.messages.stream(
            model=self.model,
            max_tokens=8192,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            for text in stream.text_stream:
                raw_parts.append(text)
                stream_callback(text)
            msg = stream.get_final_message()
            if hasattr(msg, "usage") and msg.usage:
                u = msg.usage
                usage = Usage(
                    input_tokens=getattr(u, "input_tokens", 0) or 0,
                    output_tokens=getattr(u, "output_tokens", 0) or 0,
                )
        return "".join(raw_parts), usage

    def _extract_usage(self, response: Any) -> Usage | None:
        u = getattr(response, "usage", None)
        if not u:
            return None
        return Usage(
            input_tokens=getattr(u, "input_tokens", 0) or 0,
            output_tokens=getattr(u, "output_tokens", 0) or 0,
        )

    def _parse_response(self, raw: str) -> CVParseResult:
        text = raw.strip()
        if "```json" in text:
            m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            text = m.group(1).strip() if m else text
        elif "```" in text:
            m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            text = m.group(1).strip() if m else text
        data = json.loads(text)
        return CVParseResult.model_validate(data)

    def parse_with_validation_fix(
        self,
        document: bytes,
        mime_type: str,
        raw: str,
        errors: str,
    ) -> tuple[CVParseResult, Usage | None]:
        """Retry parse with validation error feedback."""
        from anthropic import Anthropic

        client = Anthropic(api_key=self._api_key)
        b64 = base64.b64encode(document).decode()
        prompt = VALIDATION_FIX_PROMPT.format(errors=errors, raw=raw)

        content: list[dict] = [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": mime_type, "data": b64},
            },
            {"type": "text", "text": prompt},
        ]

        response = client.messages.create(
            model=self.model,
            max_tokens=8192,
            messages=[{"role": "user", "content": content}],
        )

        raw_out = ""
        for block in response.content:
            if hasattr(block, "text") and block.text:
                raw_out = block.text
                break

        usage = self._extract_usage(response)
        return self._parse_response(raw_out), usage
