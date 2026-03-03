# Professor CV Parser

Extract structured data (publications, presentations, recognitions) from professor CVs for business graduate schools.

## Setup (uv)

```bash
uv sync
```

Create a `.env` file in the project root with your OpenAI API key:

```
OPENAI_API_KEY=sk-your-key-here
```

## Using the Notebook

1. **Add CVs** — Place PDF or DOCX files in `cv/`.

2. **Open the notebook** — `notebooks/batch_cv_parser.ipynb` in Jupyter or VS Code.

3. **Select the kernel** — Use the project’s Python environment (e.g. `cv-parser` or the venv from `uv sync`).

4. **Run all cells** — Execute top to bottom. The notebook will:
   - Extract lines and metadata from each CV
   - Send line metadata to the OpenAI API for structured extraction
   - Write output to `output/combined.csv` (or JSON)

5. **Monitor progress** — `tail -f tmp/batch_progress.txt` while cells 9–10 run.

### Configuration (cell 1)

| Variable | Default | Description |
|----------|---------|-------------|
| `CV_INPUT_DIR` | `cv/` | Directory containing PDF/DOCX files |
| `OUTPUT_FILE` | `output/combined.csv` | Final output path |
| `MAX_WORKERS` | 2 | Parallel LLM calls |
| `OPENAI_MODEL` | from .env | e.g. `gpt-4o`, `gpt-4o-mini` |
| `CHUNK_SIZE` | 80 | Max objects per LLM call; 0 = no chunking |
| `VALIDATION_MAX_TRIES` | 1 | Max revision attempts when validation fails |
| `DEDUPLICATE_ROWS` | True | Merge duplicate title+year rows |

### First run: NLTK data

If NLTK data is missing, run once in a notebook cell:

```python
import nltk
nltk.download("punkt")
nltk.download("punkt_tab")
```

## AI Engineering Techniques

| Technique | Implementation |
|-----------|----------------|
| **Line-level metadata** | Send structured line metadata (line_number, ml_category, nearest_ml_category) to the LLM instead of raw text; reduces token usage and improves extraction accuracy |
| **Pre-LLM classification** | Rule-based header detection via format hints (font size, bold, heading styles) and keyword matching with NLTK SnowballStemmer; pre-categorizes publication/presentation/recognition to guide the LLM |
| **Context propagation** | `nearest_ml_category` carries document structure so content lines inherit category from the header above them; avoids misclassification when content mentions multiple types |
| **Chunking** | Split large documents into `CHUNK_SIZE` objects per LLM call to stay within context limits |
| **Parallel processing** | `ThreadPoolExecutor` with `MAX_WORKERS` for parallel LLM calls across CVs and chunks |
| **Temperature=0** | Deterministic outputs for reproducibility |
| **Pydantic validation** | `PublicationProposed`, `PresentationProposed`, `RecognitionProposed` schemas enforce output structure |
| **Validation + retry** | Invalid outputs trigger `REVISION_PROMPT_TEMPLATE`; up to `VALIDATION_MAX_TRIES` revision attempts per chunk |
| **Line merging** | Rule-based merge of continuation lines (line wrap, authors, venue) before LLM to reduce fragmented items |
| **merge_candidate_with_next** | When extraction is incomplete (truncated title, missing journal), prompt instructs LLM to merge with next line and re-extract |
| **Domain hints** | Journal abbreviation map (JAE, JAR, JF, etc.), type hints from `matched_stem` (e.g. "journal"→type journal) |
| **Post-processing** | Institution inference from line text when empty; deduplication by filename+asset_type+title+year (prefer published over in_progress) |
| **Truncated JSON repair** | `_repair_truncated_json` recovers from incomplete LLM responses |

## Output

CSV columns: `filename`, `asset_type`, `year`, `title`, `asset_sub_type`, `status`, `role`, `institution`.
