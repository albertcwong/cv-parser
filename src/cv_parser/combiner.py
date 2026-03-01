"""Combine multiple CV parse outputs into one structure."""

import json
from pathlib import Path

from cv_parser.schemas import CVParseResult

FLAT_HEADERS = [
    "filename",
    "asset_type",
    "year",
    "title",
    "asset_sub_type",
    "status",
    "role",
    "institution",
]


def flatten_result(result: CVParseResult) -> list[dict]:
    """Flatten a single CVParseResult into rows with FLAT_HEADERS columns."""
    rows = []
    fn = result.metadata.filename or ""
    for p in result.publications:
        rows.append({
            "filename": fn,
            "asset_type": "publication",
            "year": str(p.year),
            "title": p.title,
            "asset_sub_type": p.type.value,
            "status": p.status.value,
            "role": p.role.value,
            "institution": p.institution,
        })
    for p in result.presentations:
        rows.append({
            "filename": fn,
            "asset_type": "presentation",
            "year": str(p.year),
            "title": p.title,
            "asset_sub_type": p.type.value,
            "status": "",
            "role": p.role.value,
            "institution": p.institution,
        })
    for r in result.recognitions:
        rows.append({
            "filename": fn,
            "asset_type": "recognition",
            "year": str(r.year),
            "title": r.title,
            "asset_sub_type": "",
            "status": "",
            "role": "",
            "institution": r.institution,
        })
    return rows


def combine_to_flat(results: list[CVParseResult]) -> list[dict]:
    """Flatten multiple CVParseResults into one list of row dicts."""
    rows = []
    for r in results:
        rows.extend(flatten_result(r))
    return rows


def load_from_json(paths: list[Path]) -> list[CVParseResult]:
    """Load CVParseResult from JSON files."""
    results = []
    for p in paths:
        data = json.loads(p.read_text())
        results.append(CVParseResult.model_validate(data))
    return results
