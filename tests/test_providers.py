"""Tests for testfix.providers module."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from testfix.providers import call_llm


def test_call_llm_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        call_llm("sys", "user", provider="bogus")


def test_call_llm_claude_mock():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Fixed code here")]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        result = call_llm("system", "user", provider="claude", model="claude-haiku-4-5")

    assert result == "Fixed code here"


def test_call_llm_openai_mock():
    mock_choice = MagicMock()
    mock_choice.message.content = "Fixed openai"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_response
        result = call_llm("system", "user", provider="openai", model="gpt-4o-mini")

    assert result == "Fixed openai"


def test_call_llm_ollama_mock():
    mock_choice = MagicMock()
    mock_choice.message.content = "Fixed ollama"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_response
        result = call_llm("system", "user", provider="ollama", model="qwen2.5:1.5b")

    assert result == "Fixed ollama"
