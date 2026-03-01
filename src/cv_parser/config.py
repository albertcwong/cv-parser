"""Persisted settings: provider, model, api_key."""

import json
import os
from pathlib import Path


def _config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "cv-parser" / "config.json"


def load_config() -> dict[str, str | int | bool | None]:
    """Load config from file. Missing keys are None."""
    p = _config_path()
    defaults = {"provider": None, "model": None, "model_extraction": None, "model_classification": None, "api_key": None, "threads": None, "two_pass": None, "retry_on_validation_error": None, "max_retries": None, "temp_dir": None, "use_extracted_text": None}
    if not p.exists():
        return defaults.copy()
    try:
        data = json.loads(p.read_text())
        threads = data.get("threads")
        if threads is not None:
            threads = int(threads) if isinstance(threads, (int, str)) else None
        retry = data.get("retry_on_validation_error")
        if retry is not None:
            retry = retry if isinstance(retry, bool) else str(retry).lower() in ("true", "1", "yes")
        two_pass = data.get("two_pass")
        if two_pass is not None:
            two_pass = two_pass if isinstance(two_pass, bool) else str(two_pass).lower() in ("true", "1", "yes")
        max_ret = data.get("max_retries")
        if max_ret is not None:
            max_ret = int(max_ret) if isinstance(max_ret, (int, str)) else None
        td = data.get("temp_dir")
        if td is not None:
            td = str(td)
        use_ext = data.get("use_extracted_text")
        if use_ext is not None:
            use_ext = use_ext if isinstance(use_ext, bool) else str(use_ext).lower() in ("true", "1", "yes")
        return {
            "provider": data.get("provider"),
            "model": data.get("model"),
            "model_extraction": data.get("model_extraction"),
            "model_classification": data.get("model_classification"),
            "api_key": data.get("api_key"),
            "threads": threads,
            "two_pass": two_pass,
            "retry_on_validation_error": retry,
            "max_retries": max_ret,
            "temp_dir": td,
            "use_extracted_text": use_ext,
        }
    except (json.JSONDecodeError, OSError):
        return defaults.copy()


def resolve(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    model_extraction: str | None = None,
    model_classification: str | None = None,
) -> tuple[str, str | None, str | None, str | None, str | None]:
    """Resolve provider, model, api_key, model_extraction, model_classification: cli > config > env > default."""
    cfg = load_config()
    p = provider or cfg.get("provider") or os.environ.get("CV_PARSER_PROVIDER", "openai")
    m = model or cfg.get("model") or os.environ.get("CV_PARSER_MODEL")
    m_ext = model_extraction or cfg.get("model_extraction") or os.environ.get("CV_PARSER_MODEL_EXTRACTION")
    m_cls = model_classification or cfg.get("model_classification") or os.environ.get("CV_PARSER_MODEL_CLASSIFICATION")
    key = api_key or cfg.get("api_key") or _api_key_for(p)
    return p, m, key, m_ext or m, m_cls or m


def _api_key_for(provider: str) -> str | None:
    keys = {
        "openai": ["OPENAI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    }
    for env in keys.get(provider, []):
        v = os.environ.get(env)
        if v:
            return v
    return None


def save_config(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    threads: int | None = None,
    two_pass: bool | None = None,
    retry_on_validation_error: bool | None = None,
    max_retries: int | None = None,
    use_extracted_text: bool | None = None,
    model_extraction: str | None = None,
    model_classification: str | None = None,
) -> None:
    """Persist config. Merges with existing; None means don't change; '' clears."""
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = dict(load_config())
    if provider is not None:
        data["provider"] = provider or None
    if model is not None:
        data["model"] = model or None
    if api_key is not None:
        data["api_key"] = api_key or None
    if threads is not None:
        data["threads"] = threads
    if two_pass is not None:
        data["two_pass"] = two_pass
    if retry_on_validation_error is not None:
        data["retry_on_validation_error"] = retry_on_validation_error
    if max_retries is not None:
        data["max_retries"] = max_retries
    if use_extracted_text is not None:
        data["use_extracted_text"] = use_extracted_text
    if model_extraction is not None:
        data["model_extraction"] = model_extraction or None
    if model_classification is not None:
        data["model_classification"] = model_classification or None
    out = {k: v for k, v in data.items() if v is not None}
    p.write_text(json.dumps(out, indent=2))


def get_threads() -> int:
    """Get configured thread count. Default 2."""
    cfg = load_config()
    t = cfg.get("threads")
    return int(t) if t is not None else 2


def get_two_pass() -> bool:
    """Get two-pass setting. Config > env CV_PARSER_TWO_PASS > default True."""
    cfg = load_config()
    if cfg.get("two_pass") is not None:
        return cfg["two_pass"]
    v = os.environ.get("CV_PARSER_TWO_PASS", "true").lower()
    return v in ("true", "1", "yes")


def get_retry_on_validation_error() -> bool:
    """Get retry-on-validation-error setting. Config > env CV_PARSER_RETRY_ON_VALIDATION_ERROR > default True."""
    cfg = load_config()
    if cfg.get("retry_on_validation_error") is not None:
        return cfg["retry_on_validation_error"]
    v = os.environ.get("CV_PARSER_RETRY_ON_VALIDATION_ERROR", "true").lower()
    return v in ("true", "1", "yes")


def get_temp_dir() -> Path:
    """Temp dir for topic classification output. Config > env CV_PARSER_TEMP_DIR > default tmp."""
    cfg = load_config()
    if cfg.get("temp_dir") is not None:
        return Path(str(cfg["temp_dir"]))
    v = os.environ.get("CV_PARSER_TEMP_DIR", "tmp")
    return Path(v)


def get_use_extracted_text() -> bool:
    """Use extracted text instead of original file. Config > env CV_PARSER_USE_EXTRACTED_TEXT > default False."""
    cfg = load_config()
    if cfg.get("use_extracted_text") is not None:
        return cfg["use_extracted_text"]
    v = os.environ.get("CV_PARSER_USE_EXTRACTED_TEXT", "false").lower()
    return v in ("true", "1", "yes")


def get_max_retries() -> int:
    """Get max retries on validation error. Config > env CV_PARSER_MAX_RETRIES > default 1."""
    cfg = load_config()
    if cfg.get("max_retries") is not None:
        return max(0, int(cfg["max_retries"]))
    v = os.environ.get("CV_PARSER_MAX_RETRIES", "1")
    try:
        return max(0, int(v))
    except ValueError:
        return 1
