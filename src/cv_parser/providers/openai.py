"""OpenAI provider adapter."""

import base64
import json
import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError as e:
    raise ImportError(
        "openai package is required for the OpenAI provider. "
        "Run: uv sync  (or pip install openai)"
    ) from e

from cv_parser.prompts import REFINEMENT_PROMPT, SYSTEM_PROMPT, VALIDATION_FIX_PROMPT
from cv_parser.schemas import CVParseResult, Usage


class OpenAIProvider:
    """OpenAI API provider using Responses API with file input."""

    DEFAULT_MODEL = "gpt-4o"

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
        client = OpenAI(api_key=self._api_key)
        b64 = base64.b64encode(document).decode()
        file_data = f"data:{mime_type};base64,{b64}"
        ext = "txt" if mime_type == "text/plain" else "pdf" if mime_type == "application/pdf" else "docx"
        filename = f"cv.{ext}"

        if prompt is None:
            prompt = SYSTEM_PROMPT
            if previous_result is not None and user_feedback:
                prompt = REFINEMENT_PROMPT.format(
                    feedback=user_feedback,
                    previous=previous_result.model_dump_json(indent=2),
                )

        content: list[dict[str, Any]] = [
            {"type": "input_file", "filename": filename, "file_data": file_data},
            {"type": "input_text", "text": prompt},
        ]

        logger.debug("Request: model=%s, doc_size=%d bytes, mime=%s", self.model, len(document), mime_type)

        if stream_callback:
            raw, usage = self._parse_stream(client, content, stream_callback)
        else:
            response = client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": content}],
                temperature=0,
            )
            raw = self._extract_text_from_response(response)
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
        """Stream response and return (raw_text, usage)."""
        raw_parts: list[str] = []
        usage: Usage | None = None

        stream = client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": content}],
            stream=True,
            temperature=0,
        )
        for event in stream:
            if getattr(event, "type", "") == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                raw_parts.append(delta)
                stream_callback(delta)
            elif getattr(event, "type", "") == "response.completed":
                resp = getattr(event, "response", None)
                if resp and hasattr(resp, "usage") and resp.usage:
                    u = resp.usage
                    usage = Usage(
                        input_tokens=getattr(u, "input_tokens", 0) or 0,
                        output_tokens=getattr(u, "output_tokens", 0) or 0,
                    )
        return "".join(raw_parts), usage

    def _extract_usage(self, response: Any) -> Usage | None:
        """Extract usage from non-streaming response."""
        u = getattr(response, "usage", None)
        if not u:
            return None
        return Usage(
            input_tokens=getattr(u, "input_tokens", 0) or 0,
            output_tokens=getattr(u, "output_tokens", 0) or 0,
        )

    def _extract_text_from_response(self, response: Any) -> str:
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "content") and item.content:
                    for c in item.content:
                        if hasattr(c, "text") and c.text:
                            return c.text
        if hasattr(response, "choices") and response.choices:
            msg = response.choices[0].message
            return getattr(msg, "content", str(msg))
        return str(response)

    def _parse_response(self, raw: str) -> CVParseResult:
        text = raw.strip()
        if "```json" in text:
            text = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            text = text.group(1).strip() if text else text
        elif "```" in text:
            text = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            text = text.group(1).strip() if text else text
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
        client = OpenAI(api_key=self._api_key)
        b64 = base64.b64encode(document).decode()
        file_data = f"data:{mime_type};base64,{b64}"
        ext = "pdf" if mime_type == "application/pdf" else "docx"
        prompt = VALIDATION_FIX_PROMPT.format(errors=errors, raw=raw)

        content: list[dict[str, Any]] = [
            {"type": "input_file", "filename": f"cv.{ext}", "file_data": file_data},
            {"type": "input_text", "text": prompt},
        ]

        response = client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": content}],
            temperature=0,
        )
        raw_out = self._extract_text_from_response(response)
        usage = self._extract_usage(response)
        return self._parse_response(raw_out), usage
