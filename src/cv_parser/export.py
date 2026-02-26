"""Export structured data to JSON or CSV."""

import csv
import json
import sys
from pathlib import Path

from cv_parser.combiner import FLAT_HEADERS
from cv_parser.schemas import CVParseResult


def export_csv(rows: list[dict], path: Path | None = None) -> None:
    """Write flat rows to CSV. path=None writes to stdout."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    out = sys.stdout if path is None else path.open("w", newline="")
    try:
        writer = csv.DictWriter(out, fieldnames=FLAT_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if path is not None:
            out.close()


def export_json(data: CVParseResult | list[CVParseResult], path: Path | None = None) -> None:
    """Write CVParseResult or list to JSON. path=None writes to stdout."""
    if isinstance(data, list):
        out_data = [r.model_dump() for r in data]
    else:
        out_data = data.model_dump()
    json_str = json.dumps(out_data, indent=2)
    if path is None:
        print(json_str)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_str)
