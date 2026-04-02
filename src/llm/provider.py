"""LLM provider abstraction layer — xAI Grok-first implementation.

Defines the interface all LLM providers must implement, plus a StubProvider
that returns placeholder text (used when no real LLM is configured).

Provider priority: grok → ollama → stub
API key for Grok is sourced from the GROK_API_KEY environment variable.
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
    def generate(
        self,
        prompt: str,
        max_tokens: int = 500,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate text from a prompt.

        Args:
            prompt: The user-facing input prompt.
            max_tokens: Maximum tokens to generate.
            system_prompt: Optional system-level instruction (overrides default).

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

    def generate(
        self,
        prompt: str,
        max_tokens: int = 500,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        # Detect what kind of generation is requested and return appropriate stub
        prompt_lower = prompt.lower()

        if "summary" in prompt_lower or "professional summary" in prompt_lower:
            text = (
                "Experienced software engineer with a strong background in "
                "building scalable applications. [LLM stub — configure GROK_API_KEY "
                "for personalized summaries.]"
            )
        elif "bullet" in prompt_lower or "rephrase" in prompt_lower or "optimize" in prompt_lower:
            text = (
                "Developed and maintained key software components contributing "
                "to system reliability. [LLM stub — configure GROK_API_KEY.]"
            )
        elif "answer" in prompt_lower or "question" in prompt_lower:
            text = "[LLM stub — unable to answer. Configure GROK_API_KEY.]"
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


class GrokProvider(BaseLLMProvider):
    """xAI Grok provider via the OpenAI-compatible API.

    Uses grok-4-1-fast-reasoning by default (cheapest xAI reasoning model).
    API key is read from the GROK_API_KEY environment variable — never
    hard-code it or store it in config files.

    Token discipline: max_tokens defaults to 400 for most tasks. Callers
    for summary/bullet generation should pass up to 600. The hard ceiling
    of 800 prevents runaway spend while allowing full summaries.

    System prompts: pass system_prompt to override the default "helpful
    assistant" behaviour with domain-specific instructions.
    """

    GROK_BASE_URL = "https://api.x.ai/v1"
    DEFAULT_MODEL = "grok-3-mini-fast-beta"
    # Hard cap for all calls — callers may pass lower values.
    # 4000 accommodates full-document generation (ResumeBuilder) in addition
    # to the typical summary (150) / bullet (80) calls.
    MAX_TOKENS_CEILING = 4000

    # Default system prompt used when callers don't supply one.
    DEFAULT_SYSTEM_PROMPT = (
        "You are a professional career coach and expert resume writer specialising "
        "in tech industry roles. Be concise and factual. Never fabricate experience, "
        "metrics, or technologies not explicitly mentioned in the provided context."
    )

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        prompt: str,
        max_tokens: int = 400,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install openai: pip install 'openai>=1.30.0'")

        capped = min(max_tokens, self.MAX_TOKENS_CEILING)
        sys_msg = system_prompt or self.DEFAULT_SYSTEM_PROMPT

        client = OpenAI(api_key=self.api_key, base_url=self.GROK_BASE_URL)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt},
            ],
            max_tokens=capped,
            temperature=0.3,  # Lower temperature for deterministic, factual output
        )
        choice = response.choices[0]
        return LLMResponse(
            text=(choice.message.content or "").strip(),
            model=self.model,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            provider="grok",
        )

    def is_available(self) -> bool:
        return bool(self.api_key)


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider. Calls the Ollama REST API."""

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 500,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        import httpx

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\n{prompt} [/INST]"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            text=data.get("response", ""),
            model=self.model,
            tokens_used=data.get("eval_count", 0),
            provider="ollama",
        )

    def is_available(self) -> bool:
        try:
            import httpx
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider (kept as optional fallback; prefer GrokProvider)."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        prompt: str,
        max_tokens: int = 500,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install openai: pip install 'openai>=1.30.0'")

        sys_msg = system_prompt or "You are a helpful professional career coach."
        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return LLMResponse(
            text=choice.message.content or "",
            model=self.model,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            provider="openai",
        )

    def is_available(self) -> bool:
        return bool(self.api_key)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider.

    Uses the anthropic SDK. API key is read from the ANTHROPIC_API_KEY
    environment variable.

    Recommended models for resume generation:
      - claude-haiku-4-5-20251001   (cheapest, fast — good for bulk)
      - claude-sonnet-4-6           (best quality — recommended)
      - claude-opus-4-6             (most capable, highest cost)
    """

    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        prompt: str,
        max_tokens: int = 500,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Install anthropic: pip install 'anthropic>=0.40.0'")

        client = anthropic.Anthropic(api_key=self.api_key)
        sys_msg = system_prompt or (
            "You are a professional career coach and expert resume writer specialising "
            "in tech industry roles. Be concise and factual. Never fabricate experience, "
            "metrics, or technologies not explicitly mentioned in the provided context."
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=sys_msg,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text if message.content else ""
        tokens_used = (
            message.usage.input_tokens + message.usage.output_tokens
            if message.usage else 0
        )
        return LLMResponse(
            text=text.strip(),
            model=self.model,
            tokens_used=tokens_used,
            provider="anthropic",
        )

    def is_available(self) -> bool:
        return bool(self.api_key)


# ── Factory ──────────────────────────────────────────────────

def get_llm_provider(config=None) -> BaseLLMProvider:
    """Get the configured LLM provider.

    Provider resolution order:
     1. grok  — if GROK_API_KEY env var is set (preferred, cheapest)
     2. ollama — if local Ollama server is reachable
     3. stub  — always available fallback

    The Grok API key must be set as the GROK_API_KEY environment variable.
    It is never stored in config files to avoid accidental credential leaks.
    """
    import os

    if config is None:
        from src.config import get_config
        config = get_config()

    provider_name = config.llm.provider

    if provider_name == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            return AnthropicProvider(
                api_key=api_key,
                model=config.llm.model or AnthropicProvider.DEFAULT_MODEL,
            )
        import logging
        logging.getLogger(__name__).warning(
            "LLM provider is 'anthropic' but ANTHROPIC_API_KEY env var is not set. "
            "Export ANTHROPIC_API_KEY=<your_key> to enable Claude. Falling back to stub."
        )

    elif provider_name == "grok":
        api_key = os.environ.get("GROK_API_KEY", "")
        # Allow model override via env var
        model_override = os.environ.get("GROK_MODEL", "")
        model = model_override or config.llm.model or GrokProvider.DEFAULT_MODEL
        if api_key:
            return GrokProvider(api_key=api_key, model=model)
        # Grok configured but no key set — warn and fall through
        import logging
        logging.getLogger(__name__).warning(
            "LLM provider is 'grok' but GROK_API_KEY env var is not set. "
            "Export GROK_API_KEY=<your_key> to enable Grok. Falling back to stub."
        )

    elif provider_name == "ollama":
        provider = OllamaProvider(
            model=config.llm.model,
            base_url=config.llm.base_url,
        )
        if provider.is_available():
            return provider

    elif provider_name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", config.llm.api_key or "")
        if api_key:
            return OpenAIProvider(api_key=api_key, model=config.llm.model)

    # Default fallback — no API calls
    return StubProvider()
