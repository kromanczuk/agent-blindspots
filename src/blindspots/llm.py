"""A small, thread-safe wrapper that asks Anthropic, OpenAI or Gemini models for a JSON object.

Every experiment talks to models only through `LLM.ask_json`, which
  * returns a parsed dict (or {} after all retries fail, so one bad call never crashes a long run),
  * records tokens and latency for each call (used for the cost comparison in Experiment 1),
  * in dry-run mode returns a caller-supplied stub without touching the network.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

PROVIDERS = ("anthropic", "openai", "gemini")
MAX_TOKENS = 4000
RETRIES = 3


@dataclass
class Reply:
    """A parsed model reply plus what it cost."""

    data: dict[str, Any]
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0

    def usage(self) -> dict[str, float]:
        return {"tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "seconds": self.seconds}


@dataclass
class LLM:
    """One model on one provider. Safe to share across worker threads."""

    provider: str
    model: str
    dry_run: bool = False
    calls: int = 0
    failures: int = 0  # calls that still failed after every retry
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise ValueError(f"provider must be one of {PROVIDERS}, got {self.provider!r}")
        self._client: Any = None
        self._api_errors: tuple[type[BaseException], ...] = ()
        if not self.dry_run:
            self._client, self._api_errors = _make_client(self.provider)

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"

    def ask_json(self, system: str, user: str, stub: dict[str, Any] | None = None) -> Reply:
        """Send one system + user prompt and parse the first JSON object in the reply.

        `stub` is what a dry run returns. Rate limits, server errors and unparseable replies are retried
        with a growing pause; after `RETRIES` attempts the call counts as a failure and returns {}.
        """
        with self._lock:
            self.calls += 1
        if self.dry_run:
            # A rough stand-in so cost accounting can be exercised without API calls.
            return Reply(dict(stub or {}), tokens_in=(len(system) + len(user)) // 4, tokens_out=50)

        start = time.perf_counter()
        for attempt in range(1, RETRIES + 1):
            try:
                text, tokens_in, tokens_out = self._complete(system, user)
                return Reply(_parse_json(text), tokens_in, tokens_out, round(time.perf_counter() - start, 3))
            except (ValueError, *self._api_errors) as e:  # ValueError covers bad or missing JSON
                log.warning("%s attempt %d/%d failed: %s", self, attempt, RETRIES, e)
                time.sleep(2 * attempt)
        with self._lock:
            self.failures += 1
        return Reply({})

    def _complete(self, system: str, user: str) -> tuple[str, int, int]:
        """One raw API call. Returns (text, input tokens, output tokens)."""
        if self.provider == "anthropic":
            r = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            return text, r.usage.input_tokens or 0, r.usage.output_tokens or 0
        if self.provider == "openai":
            r = self._client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return r.choices[0].message.content or "", r.usage.prompt_tokens or 0, r.usage.completion_tokens or 0
        r = self._client.models.generate_content(
            model=self.model,
            contents=user,
            config={"system_instruction": system, "response_mime_type": "application/json"},
        )
        u = r.usage_metadata
        return r.text or "", u.prompt_token_count or 0, u.candidates_token_count or 0


def _make_client(provider: str) -> tuple[Any, tuple[type[BaseException], ...]]:
    """Create the SDK client (keys come from the environment) and the exception types worth retrying."""
    if provider == "anthropic":
        import anthropic

        return anthropic.Anthropic(), (anthropic.APIError,)
    if provider == "openai":
        import openai

        return openai.OpenAI(), (openai.APIError,)
    from google import genai
    from google.genai import errors

    return genai.Client(), (errors.APIError,)


def _parse_json(text: str) -> dict[str, Any]:
    """Models sometimes wrap JSON in prose or code fences: take the outermost {...}."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    data = json.loads(match.group(0))  # json.JSONDecodeError is a ValueError
    if not isinstance(data, dict):
        raise ValueError("reply is not a JSON object")
    return data
