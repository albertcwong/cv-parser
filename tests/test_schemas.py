"""Tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from cv_parser.schemas import (
    CVParseResult,
    Presentation,
    PresentationType,
    ProfessorMetadata,
    Publication,
    PublicationRole,
    PublicationStatus,
    PublicationType,
    Recognition,
)


def test_publication_valid():
    p = Publication(
        year=2023,
        type=PublicationType.journal,
        status=PublicationStatus.published,
        institution="Journal of Finance",
        title="Market Efficiency",
        role=PublicationRole.co_author,
    )
    assert p.year == 2023
    assert p.type == PublicationType.journal


def test_publication_year_coerce():
    p = Publication(
        year="2023",
        type="journal",
        status="published",
        institution="JOF",
        title="X",
        role="co_author",
    )
    assert p.year == 2023


def test_presentation_valid():
    p = Presentation(
        title="Keynote",
        year=2024,
        type=PresentationType.keynote,
        role="sole_presenter",
        institution="AFA",
    )
    assert p.year == 2024
    assert p.type == PresentationType.keynote


def test_recognition_valid():
    r = Recognition(year=2022, title="Best Paper", institution="AoM")
    assert r.year == 2022


def test_professor_metadata_defaults():
    m = ProfessorMetadata()
    assert m.name == ""
    assert m.email == ""
    assert m.phone == ""


def test_professor_metadata_full():
    m = ProfessorMetadata(name="Jane Doe", email="jane@edu", phone="+1-555-1234")
    assert m.name == "Jane Doe"
    assert m.email == "jane@edu"
    assert m.phone == "+1-555-1234"


def test_cv_parse_result_empty():
    r = CVParseResult()
    assert r.metadata.name == ""
    assert r.publications == []
    assert r.presentations == []
    assert r.recognitions == []


def test_cv_parse_result_with_metadata():
    r = CVParseResult(
        metadata=ProfessorMetadata(name="John Smith", email="john@uni.edu"),
        publications=[],
    )
    assert r.metadata.name == "John Smith"
    assert r.metadata.email == "john@uni.edu"
    assert r.metadata.phone == ""


def test_cv_parse_result_full():
    r = CVParseResult(
        publications=[
            Publication(
                year=2023,
                type=PublicationType.journal,
                status=PublicationStatus.published,
                institution="JOF",
                title="X",
                role=PublicationRole.co_author,
            )
        ],
        presentations=[],
        recognitions=[],
    )
    assert len(r.publications) == 1
    assert r.model_dump_json()
