"""Tests for config module."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cv_parser.config import (
    get_max_retries,
    get_retry_on_validation_error,
    get_temp_dir,
    get_threads,
    get_two_pass,
    load_config,
    resolve,
    save_config,
)


def test_load_config_missing(tmp_path):
    """Missing config returns None for all keys."""
    with patch("cv_parser.config._config_path", return_value=tmp_path / "nonexistent.json"):
        cfg = load_config()
    assert cfg["provider"] is None
    assert cfg["model"] is None
    assert cfg["api_key"] is None


def test_save_and_load_config(tmp_path):
    """save_config persists; load_config reads."""
    config_file = tmp_path / "config.json"
    with patch("cv_parser.config._config_path", return_value=config_file):
        save_config(provider="anthropic", model="claude-3", api_key="sk-test")
        cfg = load_config()
    assert cfg["provider"] == "anthropic"
    assert cfg["model"] == "claude-3"
    assert cfg["api_key"] == "sk-test"


def test_save_config_merges(tmp_path):
    """save_config merges with existing; None means don't change."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"provider": "openai", "model": "gpt-4"}))
    with patch("cv_parser.config._config_path", return_value=config_file):
        save_config(provider="anthropic")
        cfg = load_config()
    assert cfg["provider"] == "anthropic"
    assert cfg["model"] == "gpt-4"


def test_resolve_uses_config(tmp_path):
    """resolve uses config when cli args are None."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"provider": "gemini", "model": "gemini-1.5"}))
    with patch("cv_parser.config._config_path", return_value=config_file):
        with patch.dict(os.environ, {}, clear=False):
            p, m, k, *_ = resolve(provider=None, model=None, api_key=None)
    assert p == "gemini"
    assert m == "gemini-1.5"


def test_get_threads_default(tmp_path):
    """get_threads returns 2 when not configured."""
    with patch("cv_parser.config._config_path", return_value=tmp_path / "nonexistent.json"):
        assert get_threads() == 2


def test_get_threads_from_config(tmp_path):
    """get_threads reads from config."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"threads": 4}))
    with patch("cv_parser.config._config_path", return_value=config_file):
        assert get_threads() == 4


def test_get_two_pass_from_config(tmp_path):
    """get_two_pass reads from config."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"two_pass": False}))
    with patch("cv_parser.config._config_path", return_value=config_file):
        assert get_two_pass() is False


def test_get_max_retries_from_config(tmp_path):
    """get_max_retries reads from config."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"max_retries": 3}))
    with patch("cv_parser.config._config_path", return_value=config_file):
        assert get_max_retries() == 3


def test_get_retry_from_config(tmp_path):
    """get_retry_on_validation_error reads from config."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"retry_on_validation_error": False}))
    with patch("cv_parser.config._config_path", return_value=config_file):
        assert get_retry_on_validation_error() is False


def test_get_temp_dir_default(tmp_path):
    """get_temp_dir returns tmp when not configured."""
    with patch("cv_parser.config._config_path", return_value=tmp_path / "nonexistent.json"):
        with patch.dict(os.environ, {}, clear=False):
            assert get_temp_dir() == Path("tmp")


def test_get_temp_dir_from_env(tmp_path):
    """get_temp_dir reads CV_PARSER_TEMP_DIR."""
    with patch("cv_parser.config._config_path", return_value=tmp_path / "nonexistent.json"):
        with patch.dict(os.environ, {"CV_PARSER_TEMP_DIR": "/custom/tmp"}, clear=False):
            assert get_temp_dir() == Path("/custom/tmp")


def test_resolve_model_extraction_classification(tmp_path):
    """resolve returns model_extraction and model_classification from config."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({
        "provider": "openai",
        "model": "gpt-4o",
        "model_extraction": "gpt-4o-mini",
        "model_classification": "gpt-4o",
    }))
    with patch("cv_parser.config._config_path", return_value=config_file):
        with patch.dict(os.environ, {}, clear=False):
            p, m, k, m_ext, m_cls = resolve(provider=None, model=None, api_key=None)
    assert m_ext == "gpt-4o-mini"
    assert m_cls == "gpt-4o"


def test_resolve_cli_overrides_config(tmp_path):
    """CLI args override config."""
    config_file = tmp_path / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"provider": "openai", "model": "gpt-4"}))
    with patch("cv_parser.config._config_path", return_value=config_file):
        p, m, k, *_ = resolve(provider="anthropic", model=None, api_key=None)
    assert p == "anthropic"
    assert m == "gpt-4"
