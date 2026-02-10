"""LLM provider abstraction layer.

Defines the interface all LLM providers must implement, plus a StubProvider
that returns placeholder text (used when no real LLM is configured).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Standard response from any LLM provider."""
    text: str
    model: str
    tokens_used: int = 0
    provider: str = "unknown"


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 500) -> LLMResponse:
        """Generate text from a prompt.

        Args:
            prompt: The input prompt.
            max_tokens: Maximum tokens to generate.

        Returns:
            LLMResponse with generated text.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        ...


class StubProvider(BaseLLMProvider):
    """Stub LLM provider — returns placeholder text.

    Used during development or when no API key is configured.
    """

    def generate(self, prompt: str, max_tokens: int = 500) -> LLMResponse:
        # Detect what kind of generation is requested and return appropriate stub
        prompt_lower = prompt.lower()

        if "summary" in prompt_lower or "professional summary" in prompt_lower:
            text = (
                "Experienced software engineer with a strong background in "
                "building scalable applications. [LLM stub — configure a real "
                "LLM provider for personalized summaries.]"
            )
        elif "bullet" in prompt_lower or "rephrase" in prompt_lower:
            text = (
                "Developed and maintained key software components contributing "
                "to system reliability. [LLM stub — configure a real LLM provider.]"
            )
        elif "answer" in prompt_lower or "question" in prompt_lower:
            text = "[LLM stub — unable to answer. Configure a real LLM provider.]"
        else:
            text = f"[LLM stub response for: {prompt[:80]}...]"

        return LLMResponse(
            text=text,
            model="stub",
            tokens_used=0,
            provider="stub",
        )

    def is_available(self) -> bool:
        return True


# ── TODO: Real providers (implement when API keys available) ──

class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider. TODO: implement when Ollama is set up."""

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def generate(self, prompt: str, max_tokens: int = 500) -> LLMResponse:
        # TODO: Implement using httpx to call Ollama API
        raise NotImplementedError("Ollama provider not yet implemented. Run `ollama serve` and implement this.")

    def is_available(self) -> bool:
        # TODO: Check if Ollama is running
        return False


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider. TODO: implement when API key is available."""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 500) -> LLMResponse:
        # TODO: Implement using openai package
        raise NotImplementedError("OpenAI provider not yet implemented. Provide API key and implement.")

    def is_available(self) -> bool:
        return bool(self.api_key)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider. TODO: implement when API key is available."""

    def __init__(self, api_key: str, model: str = "gemini-pro"):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 500) -> LLMResponse:
        # TODO: Implement using google-generativeai package
        raise NotImplementedError("Gemini provider not yet implemented.")

    def is_available(self) -> bool:
        return bool(self.api_key)


# ── Factory ──────────────────────────────────────────────────

def get_llm_provider(config=None) -> BaseLLMProvider:
    """Get the configured LLM provider.

    Falls back to StubProvider if the configured provider isn't available.
    """
    if config is None:
        from src.config import get_config
        config = get_config()

    provider_name = config.llm.provider

    if provider_name == "ollama":
        provider = OllamaProvider(
            model=config.llm.model,
            base_url=config.llm.base_url,
        )
        if provider.is_available():
            return provider

    elif provider_name == "openai" and config.llm.api_key:
        provider = OpenAIProvider(
            api_key=config.llm.api_key,
            model=config.llm.model,
        )
        if provider.is_available():
            return provider

    elif provider_name == "gemini" and config.llm.api_key:
        provider = GeminiProvider(
            api_key=config.llm.api_key,
            model=config.llm.model,
        )
        if provider.is_available():
            return provider

    # Default fallback
    return StubProvider()
