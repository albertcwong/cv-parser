# Professor CV Parser

Extract structured data (publications, presentations, recognitions) from professor CVs for business graduate schools.

## Setup

```bash
# With uv (recommended)
uv sync
uv sync --extra anthropic   # or --extra gemini
uv sync --extra anthropic --extra gemini   # multiple extras

# With pip
pip install -e ".[openai]"   # or [anthropic] or [gemini]
pip install -e ".[anthropic,gemini]"   # multiple extras

# Optional: fzf for a better file picker (Tab=select, Enter=confirm)
uv sync --extra fzf   # requires fzf installed: https://github.com/junegunn/fzf
```

**API key**: Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`. Or configure via interactive Settings (stored in `~/.config/cv-parser/config.json`, outside the repo).

## Config

Settings are persisted in `~/.config/cv-parser/config.json` (or `$XDG_CONFIG_HOME/cv-parser/config.json`). Env vars override config.

| Setting | Env var | Default |
|---------|---------|---------|
| Provider | `CV_PARSER_PROVIDER` | openai |
| Model | `CV_PARSER_MODEL` | provider default |
| Two-pass | `CV_PARSER_TWO_PASS` | true |
| Retry on validation error | `CV_PARSER_RETRY_ON_VALIDATION_ERROR` | true |
| Max retries | `CV_PARSER_MAX_RETRIES` | 1 |
| Parse threads | — | 2 |

## CLI Usage

### Parse a CV

```bash
# One-shot parse (JSON to stdout)
python -m cv_parser path/to/cv.pdf

# Parse and save to file
python -m cv_parser path/to/cv.pdf -o output.json

# Options
python -m cv_parser --provider openai --model gpt-4o path/to/cv.pdf
python -m cv_parser --two-pass path/to/cv.pdf   # two-pass extraction (default)
python -m cv_parser --no-two-pass path/to/cv.pdf
python -m cv_parser --max-retries 2 path/to/cv.pdf
```

### Batch parse (CLI)

```bash
python -m cv_parser file1.pdf file2.pdf --output-dir ./out
# Optional: consolidate to CSV
python -m cv_parser file1.pdf file2.pdf --output-dir ./out --consolidate ./out/combined.csv
```

### Interactive mode

```bash
python -m cv_parser -i
# or: python -m cv_parser
```

Menu:

1. **Parse one CV** — interactive, verify before saving
2. **Parse many CVs** — queue files, process in background; choose layout (individual/combined) and format (JSON/CSV)
3. **Job status** — monitor parse queue and progress (auto-refresh every 2s)
4. **Export parsed CV** — select JSON files, choose CSV or JSON export; specify file or directory (dir → `combined.csv`/`combined.json` inside)
5. **Settings** — provider, model, API key, parse threads, two-pass, retry on validation error, max retries
6. **Quit**

### Export (consolidate multiple JSON outputs)

```bash
# Non-interactive: specify files and output path
python -m cv_parser export file1.json file2.json -o consolidated.csv

# Output to stdout
python -m cv_parser export file1.json file2.json
```

Export produces a flat CSV with headers: `name`, `email`, `phone`, `asset_type`, `year`, `title`, `asset_sub_type`, `status`, `institution`, `role`.

## Contributing

```bash
# Install with dev dependencies
uv sync --group dev
# or: pip install -e ".[openai,dev]"

# Run tests
uv run pytest
# or: pytest
```
