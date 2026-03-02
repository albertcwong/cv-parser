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
| `DEDUPLICATE_ROWS` | True | Merge duplicate title+year rows |

### First run: NLTK data

If NLTK data is missing, run once in a notebook cell:

```python
import nltk
nltk.download("punkt")
nltk.download("punkt_tab")
```

## Output

CSV columns: `filename`, `asset_type`, `year`, `title`, `asset_sub_type`, `status`, `role`, `institution`.
