"""Google Gemini provider adapter."""

import base64
import json
import logging
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cv_parser.prompts import REFINEMENT_PROMPT, SYSTEM_PROMPT, VALIDATION_FIX_PROMPT
from cv_parser.schemas import CVParseResult, Usage

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Google Gemini API provider. PDF supported; docx converted to PDF."""

    DEFAULT_MODEL = "gemini-1.5-pro"

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
        import google.generativeai as genai

        genai.configure(api_key=self._api_key)

        if mime_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            document, mime_type = self._docx_to_pdf(document)

        if prompt is None:
            prompt = SYSTEM_PROMPT
            if previous_result is not None and user_feedback:
                prompt = REFINEMENT_PROMPT.format(
                    feedback=user_feedback,
                    previous=previous_result.model_dump_json(indent=2),
                )

        model = genai.GenerativeModel(self.model)
        logger.debug("Request: model=%s, doc_size=%d bytes, mime=%s", self.model, len(document), mime_type)
        if mime_type == "text/plain":
            content = f"Document text:\n{document.decode('utf-8')}\n\n{prompt}"
        else:
            file = genai.upload_file(mime_type=mime_type, file_data=document)
            content = [file, prompt]

        if stream_callback:
            raw, usage = self._parse_stream(model, content, stream_callback)
        else:
            response = model.generate_content(content)
            raw = response.text if response.text else str(response)
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
        self, model: Any, content: Any, stream_callback: Callable[[str], None]
    ) -> tuple[str, Usage | None]:
        raw_parts: list[str] = []
        usage: Usage | None = None
        for chunk in model.generate_content(content, stream=True):
            if chunk.text:
                raw_parts.append(chunk.text)
                stream_callback(chunk.text)
            usage = self._extract_usage(chunk)
        return "".join(raw_parts), usage

    def _extract_usage(self, response: Any) -> Usage | None:
        um = getattr(response, "usage_metadata", None)
        if not um:
            return None
        inp = getattr(um, "prompt_token_count", None) or 0
        out = getattr(um, "candidates_token_count", None) or getattr(um, "total_token_count", None) or 0
        return Usage(input_tokens=inp, output_tokens=out)

    def _docx_to_pdf(self, document: bytes) -> tuple[bytes, str]:
        """Convert docx to PDF for Gemini (no native docx support)."""
        try:
            import subprocess
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
                f.write(document)
                docx_path = f.name
            out_dir = str(Path(docx_path).parent)
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, docx_path],
                check=True,
                capture_output=True,
            )
            pdf_path = Path(docx_path).with_suffix(".pdf")
            pdf_bytes = pdf_path.read_bytes()
            Path(docx_path).unlink(missing_ok=True)
            pdf_path.unlink(missing_ok=True)
            return pdf_bytes, "application/pdf"
        except Exception:
            try:
                from docx import Document as DocxDocument
                from io import BytesIO
                doc = DocxDocument(BytesIO(document))
                text = "\n".join(p.text for p in doc.paragraphs)
                return text.encode("utf-8"), "text/plain"
            except Exception:
                raise ValueError("Gemini requires PDF. Install LibreOffice for docx, or convert manually.")

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
        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        if mime_type and "word" in mime_type:
            document, mime_type = self._docx_to_pdf(document)

        prompt = VALIDATION_FIX_PROMPT.format(errors=errors, raw=raw)
        model = genai.GenerativeModel(self.model)
        file = genai.upload_file(mime_type=mime_type or "application/pdf", file_data=document)
        response = model.generate_content([file, prompt])
        raw_out = response.text if response.text else str(response)
        usage = self._extract_usage(response)
        return self._parse_response(raw_out), usage
