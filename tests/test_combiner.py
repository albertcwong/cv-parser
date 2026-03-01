"""Tests for combiner."""

import json
import tempfile
from pathlib import Path

import pytest

from cv_parser.combiner import (
    FLAT_HEADERS,
    combine_to_flat,
    flatten_result,
    load_from_json,
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
        metadata=ProfessorMetadata(filename="jane.pdf"),
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
    assert pub_row["filename"] == "jane.pdf"
    assert pub_row["asset_type"] == "publication"
    assert pub_row["year"] == "2020"
    assert pub_row["asset_sub_type"] == "journal"
    assert pub_row["status"] == "published"

    rec_row = next(x for x in rows if x["asset_type"] == "recognition")
    assert rec_row["asset_sub_type"] == ""
    assert rec_row["status"] == ""
    assert rec_row["role"] == ""


def test_combine_to_flat():
    r1 = _sample_result()
    r2 = CVParseResult(
        metadata=ProfessorMetadata(filename="john.pdf"),
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
    rows = combine_to_flat([r1, r2])
    assert len(rows) == 4
    filenames = {r["filename"] for r in rows}
    assert filenames == {"jane.pdf", "john.pdf"}


def test_load_from_json():
    r = _sample_result()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        Path(f.name).write_text(r.model_dump_json(indent=2))
        path = Path(f.name)
    try:
        results = load_from_json([path])
        assert len(results) == 1
        assert results[0].metadata.filename == "jane.pdf"
    finally:
        path.unlink()
