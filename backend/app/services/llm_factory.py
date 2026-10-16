"""LLM adapters.

Two implementations behind one port:

* ``HeuristicLLMAdapter`` — deterministic, offline, zero-dependency. It turns
  numbers into prose using fixed templates. This is the default so that the
  graph runs end-to-end on a laptop with no API key and produces the same
  verdict on every run.
* ``OpenAILLMAdapter`` — calls any OpenAI-compatible ``/chat/completions``
  endpoint. Used for the qualitative wording only; never for a number, and
  always with ``temperature=0``.

Both are side-effect free: the same inputs give the same text.
"""
from __future__ import annotations

from app.config import Settings
from app.domain.ports import LLMPort


class HeuristicLLMAdapter:
    """Deterministic qualitative reasoning."""

    name = "heuristic"

    def complete(self, system: str, user: str) -> str:
        return user


class OpenAILLMAdapter:
    """OpenAI-compatible chat completion. Requires an API key in settings."""

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def complete(self, system: str, user: str) -> str:
        if not self._settings.llm_api_key:
            raise RuntimeError(
                "LLM_API_KEY is not configured; set LLM_PROVIDER=heuristic to "
                "run the deterministic adapter instead"
            )
        import json
        import urllib.request

        body = json.dumps(
            {
                "model": self._settings.llm_model,
                "temperature": self._settings.llm_temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self._settings.llm_base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.llm_api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(  # noqa: S310 — URL comes from settings
            request, timeout=self._settings.llm_timeout_s
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM response contained no choices")
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise RuntimeError("LLM response message had no string content")
        return content


def build_llm(settings: Settings) -> LLMPort:
    if settings.llm_provider == "openai" and settings.llm_api_key:
        return OpenAILLMAdapter(settings)
    return HeuristicLLMAdapter()
