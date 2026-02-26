"""Tests for provider factory."""

import os

import pytest

from cv_parser.providers import get_provider


def test_get_provider_openai():
    """OpenAI provider can be instantiated."""
    p = get_provider(provider="openai")
    assert p is not None


def test_get_provider_anthropic():
    """Anthropic provider can be instantiated."""
    p = get_provider(provider="anthropic")
    assert p is not None


def test_get_provider_gemini():
    """Gemini provider can be instantiated."""
    p = get_provider(provider="gemini")
    assert p is not None


def test_get_provider_unknown():
    """Unknown provider raises ValueError."""
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider(provider="unknown")
