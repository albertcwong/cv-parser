"""Tests for export."""

import csv
import json
import io
import tempfile
from pathlib import Path

import pytest

from cv_parser.combiner import FLAT_HEADERS, flatten_result
from cv_parser.export import export_csv, export_json
from cv_parser.schemas import (
    CVParseResult,
    Presentation,
    PresentationRole,
    PresentationType,
    ProfessorMetadata,
    Publication,
    PublicationRole,
    PublicationStatus,
    PublicationType,
    Recognition,
)


def _sample_result() -> CVParseResult:
    return CVParseResult(
        metadata=ProfessorMetadata(name="Jane Doe"),
        publications=[
            Publication(
                year=2020,
                type=PublicationType.journal,
                status=PublicationStatus.published,
                institution="Acme",
                title="A Paper",
                role=PublicationRole.co_author,
            ),
        ],
        presentations=[
            Presentation(
                title="A Talk",
                year=2021,
                type=PresentationType.conference,
                role=PresentationRole.sole_presenter,
                institution="Conf",
            ),
        ],
        recognitions=[Recognition(year=2022, title="Award", institution="Org")],
    )


def test_export_csv_headers():
    rows = flatten_result(_sample_result())
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = Path(f.name)
    try:
        export_csv(rows, path)
        text = path.read_text()
        reader = csv.DictReader(io.StringIO(text))
        assert reader.fieldnames == FLAT_HEADERS
        data = list(reader)
        assert len(data) == 3
        for row in data:
            assert len(row) == len(FLAT_HEADERS)
    finally:
        path.unlink()


def test_export_json_single():
    r = _sample_result()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = Path(f.name)
    try:
        export_json(r, path)
        data = json.loads(path.read_text())
        assert data["metadata"]["name"] == "Jane Doe"
        assert len(data["publications"]) == 1
    finally:
        path.unlink()


def test_export_json_list():
    r = _sample_result()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = Path(f.name)
    try:
        export_json([r, r], path)
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["metadata"]["name"] == "Jane Doe"
    finally:
        path.unlink()
