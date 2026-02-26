"""Deprecated: use combiner and export modules. Re-exports for backward compat."""

import sys
from pathlib import Path

from cv_parser.combiner import (
    FLAT_HEADERS,
    combine_to_flat,
    flatten_result,
    load_from_json,
)
from cv_parser.export import export_csv

__all__ = ["FLAT_HEADERS", "consolidate_to_flat", "export_flat_csv", "flatten_result", "load_results", "run_export"]


def consolidate_to_flat(results):
    return combine_to_flat(results)


def load_results(paths: list[Path]):
    return load_from_json(paths)


def export_flat_csv(rows, path: Path | None = None):
    export_csv(rows, path)


def run_export(paths: list[Path], output_path: Path | None) -> None:
    results = load_from_json(paths)
    rows = combine_to_flat(results)
    export_csv(rows, output_path)
    if output_path:
        print(f"Wrote {output_path}", file=sys.stderr)
