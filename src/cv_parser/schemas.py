"""Pydantic schemas for CV parse results."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


@dataclass
class Usage:
    """Token usage from LLM response."""

    input_tokens: int
    output_tokens: int


class PublicationType(str, Enum):
    book = "book"
    journal = "journal"
    other = "other"


class PublicationStatus(str, Enum):
    in_progress = "in_progress"
    published = "published"


class PublicationRole(str, Enum):
    sole_author = "sole_author"
    co_author = "co_author"


class PresentationType(str, Enum):
    conference = "conference"
    keynote = "keynote"
    media = "media"
    workshop = "workshop"
    other = "other"


class PresentationRole(str, Enum):
    sole_presenter = "sole_presenter"
    co_presenter = "co_presenter"


class Publication(BaseModel):
    year: int = Field(..., ge=1950, le=2030)
    type: PublicationType
    status: PublicationStatus
    institution: str
    title: str
    role: PublicationRole

    @field_validator("year", mode="before")
    @classmethod
    def coerce_year(cls, v: Any) -> Any:
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v


class Presentation(BaseModel):
    title: str
    year: int = Field(..., ge=1950, le=2030)
    type: PresentationType
    role: PresentationRole
    institution: str

    @field_validator("year", mode="before")
    @classmethod
    def coerce_year(cls, v: Any) -> Any:
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v


class Recognition(BaseModel):
    year: int = Field(..., ge=1950, le=2030)
    title: str
    institution: str


class ProfessorMetadata(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""


class CVParseResult(BaseModel):
    metadata: ProfessorMetadata = Field(default_factory=ProfessorMetadata)
    publications: list[Publication] = Field(default_factory=list)
    presentations: list[Presentation] = Field(default_factory=list)
    recognitions: list[Recognition] = Field(default_factory=list)


class RawItem(BaseModel):
    """Minimal item from extraction pass."""

    title: str
    year: int | None = None
    institution: str = ""
    snippet: str = ""


class RawExtraction(BaseModel):
    """Output of extraction pass (Pass 1)."""

    raw_publications: list[RawItem] = Field(default_factory=list)
    raw_presentations: list[RawItem] = Field(default_factory=list)
    raw_recognitions: list[RawItem] = Field(default_factory=list)
