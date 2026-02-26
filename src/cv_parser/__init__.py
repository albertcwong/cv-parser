"""Professor CV parser for business graduate schools."""

from cv_parser.schemas import CVParseResult, ProfessorMetadata, Publication, Presentation, Recognition
from cv_parser.parser import parse_cv

__all__ = [
    "CVParseResult",
    "ProfessorMetadata",
    "Publication",
    "Presentation",
    "Recognition",
    "parse_cv",
]
