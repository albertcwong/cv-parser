"""CV parser orchestration."""

import json
import os
import re
from pathlib import Path

from cv_parser.prompts import (
    CLASSIFICATION_PROMPT,
    CLASSIFICATION_REFINEMENT_PROMPT,
    EXTRACTION_PROMPT,
)
from cv_parser.providers import get_provider
from cv_parser.schemas import (
    CVParseResult,
    Presentation,
    Publication,
    RawExtraction,
    Recognition,
    Usage,
)


def _dedupe_raw_extraction(raw: dict) -> dict:
    """Deduplicate raw extraction items by (title, year). Keep first occurrence."""
    def dedupe_items(items: list, key_fn):
        seen: set = set()
        out: list = []
        for it in items:
            if isinstance(it, dict):
                k = key_fn(it.get("title", ""), it.get("year"))
            else:
                k = key_fn(getattr(it, "title", ""), getattr(it, "year", None))
            if k not in seen:
                seen.add(k)
                out.append(it)
        return out

    key_fn = lambda t, y: (str(t).lower().strip(), y if y is not None else -1)
    return {
        "raw_publications": dedupe_items(raw.get("raw_publications", []), key_fn),
        "raw_presentations": dedupe_items(raw.get("raw_presentations", []), key_fn),
        "raw_recognitions": dedupe_items(raw.get("raw_recognitions", []), key_fn),
    }


def _dedupe_result(result: CVParseResult) -> CVParseResult:
    """Remove duplicate entries by (title, year). Keep first occurrence."""
    seen_pub: set[tuple[str, int]] = set()
    pubs: list[Publication] = []
    for p in result.publications:
        key = (p.title.lower().strip(), p.year)
        if key not in seen_pub:
            seen_pub.add(key)
            pubs.append(p)

    seen_pres: set[tuple[str, int]] = set()
    pres: list[Presentation] = []
    for p in result.presentations:
        key = (p.title.lower().strip(), p.year)
        if key not in seen_pres:
            seen_pres.add(key)
            pres.append(p)

    seen_rec: set[tuple[str, int]] = set()
    recs: list[Recognition] = []
    for r in result.recognitions:
        key = (r.title.lower().strip(), r.year)
        if key not in seen_rec:
            seen_rec.add(key)
            recs.append(r)

    return CVParseResult(metadata=result.metadata, publications=pubs, presentations=pres, recognitions=recs)


MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
}

SCHEMA_JSON = json.dumps(CVParseResult.model_json_schema(), indent=2)


def estimate_tokens_from_bytes(n_bytes: int) -> int:
    """Rough token estimate: bytes → words (~5 chars) → tokens (~1.3/word). ~bytes/4."""
    return max(1, n_bytes // 4)


def estimate_tokens_from_text(text: str) -> int:
    """Rough token estimate from streamed text. ~4 chars per token."""
    return max(0, len(text) // 4)


def _parse_json_from_response(raw: str) -> dict:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    text = raw.strip()
    if "```json" in text:
        m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        text = m.group(1).strip() if m else text
    elif "```" in text:
        m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        text = m.group(1).strip() if m else text
    return json.loads(text)


def parse_two_pass(
    prov,
    document: bytes,
    mime: str,
    *,
    stream_callback=None,
    retry_on_validation_error: bool = True,
    max_retries: int = 1,
    previous_result: CVParseResult | None = None,
    user_feedback: str | None = None,
    on_classification_start=None,
) -> tuple[CVParseResult, Usage | None]:
    """Two-pass extraction: extract all items, then classify each."""
    raw1, usage1 = prov.parse(
        document,
        mime,
        prompt=EXTRACTION_PROMPT,
        retry_on_validation_error=False,
        return_raw=True,
        stream_callback=stream_callback,
    )
    raw_extraction = _parse_json_from_response(raw1)
    try:
        RawExtraction.model_validate(raw_extraction)
    except Exception:
        pass  # use dict as-is

    raw_extraction = _dedupe_raw_extraction(raw_extraction)
    raw_extraction_str = json.dumps(raw_extraction, indent=2)
    if previous_result is not None and user_feedback:
        class_prompt = CLASSIFICATION_REFINEMENT_PROMPT.format(
            feedback=user_feedback,
            previous=previous_result.model_dump_json(indent=2),
            raw_extraction=raw_extraction_str,
        )
    else:
        class_prompt = CLASSIFICATION_PROMPT.format(
            raw_extraction=raw_extraction_str,
            schema=SCHEMA_JSON,
        )

    if on_classification_start:
        on_classification_start()

    result, usage2 = prov.parse(
        document,
        mime,
        prompt=class_prompt,
        retry_on_validation_error=retry_on_validation_error,
        max_retries=max_retries,
        stream_callback=stream_callback,
    )
    total_usage = None
    if usage1 and usage2:
        total_usage = Usage(
            input_tokens=usage1.input_tokens + usage2.input_tokens,
            output_tokens=usage1.output_tokens + usage2.output_tokens,
        )
    elif usage2:
        total_usage = usage2
    elif usage1:
        total_usage = usage1
    return _dedupe_result(result), total_usage


def parse_cv(
    path: Path | str,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    retry_on_validation_error: bool | None = None,
    max_retries: int | None = None,
    two_pass: bool = False,
) -> CVParseResult:
    """Parse a CV file to structured data."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    mime = MIME.get(suffix)
    if not mime:
        raise ValueError(f"Unsupported format: {suffix}. Use .pdf or .docx")

    if retry_on_validation_error is None:
        retry_on_validation_error = os.environ.get(
            "CV_PARSER_RETRY_ON_VALIDATION_ERROR", "true"
        ).lower() in ("true", "1", "yes")
    if max_retries is None:
        try:
            from cv_parser.config import get_max_retries
            max_retries = get_max_retries() if retry_on_validation_error else 0
        except ImportError:
            max_retries = 1 if retry_on_validation_error else 0

    document = path.read_bytes()
    prov = get_provider(provider=provider, model=model, api_key=api_key)

    if two_pass:
        result, _ = parse_two_pass(
            prov,
            document,
            mime,
            retry_on_validation_error=retry_on_validation_error,
            max_retries=max_retries,
        )
        return result

    result, _ = prov.parse(
        document,
        mime,
        retry_on_validation_error=retry_on_validation_error,
        max_retries=max_retries,
    )
    return result


def parse_cvs(
    paths: list[Path],
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    retry_on_validation_error: bool = True,
    max_retries: int | None = None,
    two_pass: bool = False,
) -> list[tuple[Path, CVParseResult]]:
    """Parse multiple CVs. Returns [(path, result), ...]. No verify loop."""
    out: list[tuple[Path, CVParseResult]] = []
    for p in paths:
        result = parse_cv(
            p,
            provider=provider,
            model=model,
            api_key=api_key,
            retry_on_validation_error=retry_on_validation_error,
            max_retries=max_retries,
            two_pass=two_pass,
        )
        out.append((p, result))
    return out
