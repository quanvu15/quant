"""
Tests for OpenAI-compatible LLMConfig — provider auto-detection, validation.
"""
from __future__ import annotations
import pytest
from pydantic import ValidationError
from models.requests.agents import LLMConfig


class TestLLMConfigAutoDetect:
    """Provider được auto-detect từ base_url."""

    def test_openai_default(self):
        cfg = LLMConfig(model="gpt-4o", api_key="sk-test")
        assert cfg.provider == "openai"
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_openai_explicit_url(self):
        cfg = LLMConfig(model="gpt-4o", api_key="sk-test", base_url="https://api.openai.com/v1")
        assert cfg.provider == "openai"

    def test_groq(self):
        cfg = LLMConfig(
            model="llama-3.1-70b-versatile",
            api_key="gsk_test",
            base_url="https://api.groq.com/openai/v1",
        )
        assert cfg.provider == "groq"

    def test_together(self):
        cfg = LLMConfig(
            model="meta-llama/Llama-3-70b-chat-hf",
            api_key="together_test",
            base_url="https://api.together.xyz/v1",
        )
        assert cfg.provider == "together"

    def test_deepseek(self):
        cfg = LLMConfig(
            model="deepseek-chat",
            api_key="ds_test",
            base_url="https://api.deepseek.com/v1",
        )
        assert cfg.provider == "deepseek"

    def test_anthropic(self):
        cfg = LLMConfig(
            model="claude-3-5-sonnet-20241022",
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
        )
        assert cfg.provider == "anthropic"

    def test_google(self):
        cfg = LLMConfig(
            model="gemini-1.5-pro",
            api_key="AIza_test",
            base_url="https://generativelanguage.googleapis.com/v1beta",
        )
        assert cfg.provider == "google"

    def test_ollama_local(self):
        cfg = LLMConfig(
            model="llama3.2",
            api_key="ollama",
            base_url="http://localhost:11434/v1",
        )
        assert cfg.provider == "openai"  # Ollama uses openai-compat

    def test_lm_studio(self):
        cfg = LLMConfig(
            model="local-model",
            api_key="lm-studio",
            base_url="http://localhost:1234/v1",
        )
        assert cfg.provider == "openai"

    def test_openrouter(self):
        cfg = LLMConfig(
            model="anthropic/claude-3.5-sonnet",
            api_key="sk-or-test",
            base_url="https://openrouter.ai/api/v1",
        )
        assert cfg.provider == "openrouter"

    def test_mistral(self):
        cfg = LLMConfig(
            model="mistral-large-latest",
            api_key="mistral_test",
            base_url="https://api.mistral.ai/v1",
        )
        assert cfg.provider == "mistral"

    def test_provider_override(self):
        """Explicit provider không bị override bởi auto-detect."""
        cfg = LLMConfig(
            model="custom-model",
            api_key="key",
            base_url="https://api.openai.com/v1",
            provider="my-custom-provider",
        )
        assert cfg.provider == "my-custom-provider"

    def test_unknown_url_defaults_to_openai(self):
        """URL không nhận ra → default openai-compat."""
        cfg = LLMConfig(
            model="some-model",
            api_key="key",
            base_url="https://my-custom-llm-server.example.com/v1",
        )
        assert cfg.provider == "openai"


class TestLLMConfigValidation:
    def test_model_required(self):
        with pytest.raises(ValidationError):
            LLMConfig(api_key="sk-test")

    def test_api_key_required(self):
        with pytest.raises(ValidationError):
            LLMConfig(model="gpt-4o")

    def test_temperature_bounds(self):
        with pytest.raises(ValidationError):
            LLMConfig(model="gpt-4o", api_key="sk", temperature=3.0)

    def test_max_tokens_bounds(self):
        with pytest.raises(ValidationError):
            LLMConfig(model="gpt-4o", api_key="sk", max_tokens=0)

    def test_defaults(self):
        cfg = LLMConfig(model="gpt-4o-mini", api_key="sk-test")
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 4096
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_serialization(self):
        """LLMConfig serialize đúng — api_key có mặt (client gửi, không store)."""
        cfg = LLMConfig(model="gpt-4o", api_key="sk-secret", base_url="https://api.openai.com/v1")
        d = cfg.model_dump()
        assert d["model"] == "gpt-4o"
        assert d["api_key"] == "sk-secret"
        assert d["base_url"] == "https://api.openai.com/v1"
        assert d["provider"] == "openai"
