"""Tests for consolidate."""

import csv
import io
import json
import tempfile
from pathlib import Path

import pytest

from cv_parser.consolidate import (
    FLAT_HEADERS,
    consolidate_to_flat,
    export_flat_csv,
    flatten_result,
    load_results,
)
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
        metadata=ProfessorMetadata(name="Jane Doe", email="jane@edu", phone="555-1234"),
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
        recognitions=[
            Recognition(year=2022, title="Award", institution="Org"),
        ],
    )


def test_flatten_result():
    r = _sample_result()
    rows = flatten_result(r)
    assert len(rows) == 3
    pub_row = next(x for x in rows if x["asset_type"] == "publication")
    assert pub_row["name"] == "Jane Doe"
    assert pub_row["email"] == "jane@edu"
    assert pub_row["asset_type"] == "publication"
    assert pub_row["year"] == "2020"
    assert pub_row["title"] == "A Paper"
    assert pub_row["asset_sub_type"] == "journal"
    assert pub_row["status"] == "published"
    assert pub_row["role"] == "co_author"

    pres_row = next(x for x in rows if x["asset_type"] == "presentation")
    assert pres_row["asset_sub_type"] == "conference"
    assert pres_row["status"] == ""
    assert pres_row["role"] == "sole_presenter"

    rec_row = next(x for x in rows if x["asset_type"] == "recognition")
    assert rec_row["asset_sub_type"] == ""
    assert rec_row["status"] == ""
    assert rec_row["role"] == ""


def test_consolidate_two_results():
    r1 = _sample_result()
    r2 = CVParseResult(
        metadata=ProfessorMetadata(name="John"),
        publications=[
            Publication(
                year=2019,
                type=PublicationType.book,
                status=PublicationStatus.in_progress,
                institution="Pub",
                title="Another",
                role=PublicationRole.sole_author,
            ),
        ],
    )
    rows = consolidate_to_flat([r1, r2])
    assert len(rows) == 4
    names = {r["name"] for r in rows}
    assert names == {"Jane Doe", "John"}


def test_export_flat_csv_headers():
    rows = flatten_result(_sample_result())
    buf = io.StringIO()
    export_flat_csv(rows, None)
    # export_flat_csv with path=None writes to stdout, not buf
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = Path(f.name)
    try:
        export_flat_csv(rows, path)
        text = path.read_text()
        reader = csv.DictReader(io.StringIO(text))
        assert reader.fieldnames == FLAT_HEADERS
        data = list(reader)
        assert len(data) == 3
        for row in data:
            assert len(row) == len(FLAT_HEADERS)
    finally:
        path.unlink()


def test_load_results():
    r = _sample_result()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        Path(f.name).write_text(r.model_dump_json(indent=2))
        path = Path(f.name)
    try:
        results = load_results([path])
        assert len(results) == 1
        assert results[0].metadata.name == "Jane Doe"
    finally:
        path.unlink()
