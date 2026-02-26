"""Combine multiple CV parse outputs into one structure."""

import json
from pathlib import Path

from cv_parser.schemas import CVParseResult

FLAT_HEADERS = [
    "name",
    "email",
    "phone",
    "asset_type",
    "year",
    "title",
    "asset_sub_type",
    "status",
    "institution",
    "role",
]


def flatten_result(result: CVParseResult) -> list[dict]:
    """Flatten a single CVParseResult into rows with FLAT_HEADERS columns."""
    rows = []
    m = result.metadata
    for p in result.publications:
        rows.append({
            "name": m.name,
            "email": m.email,
            "phone": m.phone,
            "asset_type": "publication",
            "year": str(p.year),
            "title": p.title,
            "asset_sub_type": p.type.value,
            "status": p.status.value,
            "institution": p.institution,
            "role": p.role.value,
        })
    for p in result.presentations:
        rows.append({
            "name": m.name,
            "email": m.email,
            "phone": m.phone,
            "asset_type": "presentation",
            "year": str(p.year),
            "title": p.title,
            "asset_sub_type": p.type.value,
            "status": "",
            "institution": p.institution,
            "role": p.role.value,
        })
    for r in result.recognitions:
        rows.append({
            "name": m.name,
            "email": m.email,
            "phone": m.phone,
            "asset_type": "recognition",
            "year": str(r.year),
            "title": r.title,
            "asset_sub_type": "",
            "status": "",
            "institution": r.institution,
            "role": "",
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
