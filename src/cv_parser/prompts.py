"""Shared prompts for CV extraction."""

import json

from cv_parser.schemas import CVParseResult

SCHEMA = CVParseResult.model_json_schema()

SYSTEM_PROMPT = f"""Extract structured data from this professor CV for a business graduate school. Output MUST be valid JSON matching this schema:

{json.dumps(SCHEMA, indent=2)}

Rules:
- metadata: name, email, phone - extract from header/contact section of the CV
- publications: year (int 1950-2030), type (book|journal|other), status (in_progress|published), institution, title, role (sole_author|co_author)
  - role sole_author: CV owner is the only author listed (compare author names to metadata.name)
  - role co_author: multiple authors listed (e.g. "Smith, J., Jones, A.") or snippet says "with X" / "co-authored with"
  - institution: for type book = publisher (e.g. Harvard Business School Press); for type journal = journal name (e.g. Academy of Management Review). Do not mix.
- presentations: title, year (int), type (conference|keynote|media|workshop|other), role (sole_presenter|co_presenter), institution
- Use type "other" for publications or presentations when the classification does not fit neatly into the listed options.
- recognitions: year (int), title, institution
- Use type (not activity_type) for presentations.
- For unknown values, omit the field or use null.
- Return ONLY the JSON object, no markdown or explanation."""

REFINEMENT_PROMPT = """The previous extraction had issues. User feedback: {feedback}

Previous result:
{previous}

Revise the extraction according to the feedback. Return ONLY the JSON object matching the schema."""

VALIDATION_FIX_PROMPT = """The JSON you returned failed validation. Errors: {errors}

Your previous output:
{raw}

Fix the JSON to match the schema. Return ONLY the valid JSON object."""

EXTRACTION_PROMPT = """Extract metadata and EVERY publication, presentation, and recognition from this professor CV. Do not skip any. Scan the entire document thoroughly.

First, extract metadata from the header/contact: name, email, phone.

For each item, capture:
- title: the item title
- year: int 1950-2030 if identifiable, else null
- institution: publisher/venue/organization if identifiable, else ""
- snippet: the exact text from the document for this item
- authors: the author string as it appears in the citation (e.g. "Smith, J." or "Smith, J., Jones, A.") — for publications only

Output MUST be valid JSON:
{
  "metadata": {"name": "...", "email": "...", "phone": "..."},
  "raw_publications": [{"title": "...", "year": 2020, "institution": "...", "snippet": "...", "authors": "..."}],
  "raw_presentations": [{"title": "...", "year": 2020, "institution": "...", "snippet": "..."}],
  "raw_recognitions": [{"title": "...", "year": 2020, "institution": "...", "snippet": "..."}],
  "raw_other": [{"title": "...", "year": null, "institution": "", "snippet": "..."}]
}

Put items in raw_other when they clearly do not fit publication, presentation, or recognition (e.g. teaching experience, committee work, education, employment history, other CV sections). Do not omit any line—capture everything.

Return ONLY the JSON object, no markdown or explanation."""

CLASSIFICATION_PROMPT = """Given the attached document and this list of extracted items, classify EACH item into the schema. Process every item. Do not omit any.

Extracted items:
{raw_extraction}

Schema:
{schema}

Rules:
- metadata: name, email, phone - extract from header/contact section of the CV
- publications: year (int 1950-2030), type (book|journal|other), status (in_progress|published), institution, title, role (sole_author|co_author)
  - role sole_author: CV owner ({cv_owner}) is the only author listed; compare authors field and snippet to metadata.name
  - role co_author: multiple authors in authors field, or snippet says "with X" / "co-authored with"
  - institution: for type book = publisher; for type journal = journal name. Do not mix.
- presentations: title, year (int), type (conference|keynote|media|workshop|other), role (sole_presenter|co_presenter), institution
- recognitions: year (int), title, institution
- Use type "other" when classification does not fit neatly.
- Return ONLY the JSON object matching the schema, no markdown or explanation."""

CLASSIFICATION_REFINEMENT_PROMPT = """User feedback: {feedback}

Previous result:
{previous}

Extracted items (unchanged):
{raw_extraction}

CV owner for role inference: {cv_owner}

Revise the classification according to the feedback. For publications: sole_author when CV owner is the only author; co_author when multiple authors or "with X". institution: publisher for books, journal name for journals. Process every item. Return ONLY the JSON object matching the schema."""
