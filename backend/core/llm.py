"""
LLM factory — returns the configured LangChain chat model.
Supports: ollama (local), fireworks (cloud), none (rule-based only).

Set in backend/.env:
  LLM_PROVIDER=ollama       # local Llama via Ollama
  LLM_PROVIDER=fireworks    # Fireworks AI cloud
  LLM_PROVIDER=none         # disable LLM entirely
"""
import os
from langchain_openai import ChatOpenAI

_provider = os.getenv('LLM_PROVIDER', 'none').lower()
_enabled  = os.getenv('ENABLE_LLM', 'false').lower() == 'true'


def get_llm(temperature: float = 0) -> ChatOpenAI | None:
    """Return configured LLM or None if disabled."""
    if not _enabled or _provider == 'none':
        return None

    if _provider == 'ollama':
        return ChatOpenAI(
            model=os.getenv('OLLAMA_MODEL', 'llama3.2'),
            api_key='ollama',                          # Ollama ignores the key
            base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1'),
            temperature=temperature,
        )

    if _provider == 'fireworks':
        return ChatOpenAI(
            model=os.getenv('FIREWORKS_MODEL', 'accounts/fireworks/models/minimax-m2p1'),
            api_key=os.getenv('FIREWORKS_API_KEY', ''),
            base_url='https://api.fireworks.ai/inference/v1',
            temperature=temperature,
        )

    return None


def is_enabled() -> bool:
    return _enabled and _provider != 'none'
