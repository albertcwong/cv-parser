"""Tests for parser."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cv_parser.parser import (
    estimate_tokens_from_bytes,
    estimate_tokens_from_text,
    parse_cv,
    parse_cvs,
)
from cv_parser.schemas import CVParseResult, ProfessorMetadata


def test_estimate_tokens_from_bytes():
    assert estimate_tokens_from_bytes(0) == 1
    assert estimate_tokens_from_bytes(4) == 1
    assert estimate_tokens_from_bytes(100) == 25


def test_estimate_tokens_from_text():
    assert estimate_tokens_from_text("") == 0
    assert estimate_tokens_from_text("hello") == 1
    assert estimate_tokens_from_text("hello world") == 2


def test_parse_cv_file_not_found():
    with pytest.raises(FileNotFoundError):
        parse_cv("/nonexistent/cv.pdf")


def test_parse_cv_unsupported_format():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"test")
        path = f.name
    try:
        with pytest.raises(ValueError, match="Unsupported format"):
            parse_cv(path)
    finally:
        Path(path).unlink()


def test_parse_cvs():
    """parse_cvs returns [(path, result), ...] for each input."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f1:
        f1.write(b"%PDF-1.4 dummy")
        p1 = Path(f1.name)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f2:
        f2.write(b"%PDF-1.4 dummy")
        p2 = Path(f2.name)
    try:
        fake_result = CVParseResult(metadata=ProfessorMetadata(name="Test"))
        with patch("cv_parser.parser.parse_cv", return_value=fake_result) as m:
            out = parse_cvs([p1, p2])
        assert m.call_count == 2
        assert len(out) == 2
        assert out[0][0] == p1 and out[0][1] == fake_result
        assert out[1][0] == p2 and out[1][1] == fake_result
    finally:
        p1.unlink()
        p2.unlink()
