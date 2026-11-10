"""
llm_client.py — Centralised NVIDIA NIM client.

All modules that need LLM calls import from here.
This means if the model or API changes, you update ONE file.

Supports:
  - Sync calls  (for jd_parser)
  - Async calls (for explainer / outreach batch generation)
  - Retry logic with exponential backoff
  - Token usage logging
"""

import asyncio
import time
from typing import List, Dict, Optional
from threading import Lock


from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL


# ── Shared clients (initialised once) ─────────────────────────────────────────
class AIUnavailable(RuntimeError):
    """AI could not produce a usable result. Never substitute success."""


_sync_client = None
_async_client = None


def sync_client():
    global _sync_client
    if not NVIDIA_API_KEY:
        raise AIUnavailable("AI service is not configured. Set NVIDIA_API_KEY on the server.")
    if _sync_client is None:
        from openai import OpenAI

        _sync_client = OpenAI(
            base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=20, max_retries=0
        )
    return _sync_client


def async_client():
    global _async_client
    if not NVIDIA_API_KEY:
        raise AIUnavailable("AI service is not configured. Set NVIDIA_API_KEY on the server.")
    if _async_client is None:
        from openai import AsyncOpenAI

        _async_client = AsyncOpenAI(
            base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=20, max_retries=0
        )
    return _async_client


# ── Sync call ──────────────────────────────────────────────────────────────────
def chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 1000,
    retries: int = 2,
) -> str:
    """
    Synchronous LLM call with retry logic.

    Args:
        messages:    OpenAI-format message list [{"role": ..., "content": ...}]
        temperature: 0.1 for structured output, 0.4-0.7 for creative text
        max_tokens:  cap on response length
        retries:     number of retry attempts on failure

    Returns:
        Response text as string
    """
    last_err = None
    for attempt in range(retries):
        try:
            response = sync_client().chat.completions.create(
                model=NVIDIA_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content.strip()
            _log_usage(response, sync=True)
            return text

        except Exception as e:
            last_err = e
            wait = 2**attempt  # exponential backoff: 1s, 2s, 4s
            print(f"[LLM] Attempt {attempt + 1}/{retries} failed: {e}. Retrying in {wait}s…")
            time.sleep(wait)

    print(f"[LLM] All {retries} attempts failed. Last error: {last_err}")
    raise AIUnavailable("AI service is unavailable. Please retry.") from last_err


# ── Async call ─────────────────────────────────────────────────────────────────
async def achat(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 1000,
    retries: int = 2,
) -> str:
    """
    Async LLM call with retry logic.
    Use this inside async functions (explainer, outreach batch).
    """
    last_err = None
    for attempt in range(retries):
        try:
            response = await async_client().chat.completions.create(
                model=NVIDIA_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content.strip()
            _log_usage(response, sync=False)
            return text

        except Exception as e:
            last_err = e
            wait = 2**attempt
            print(f"[LLM-async] Attempt {attempt + 1}/{retries} failed: {e}. Retrying in {wait}s…")
            await asyncio.sleep(wait)

    print(f"[LLM-async] All {retries} attempts failed. Last: {last_err}")
    raise AIUnavailable("AI service is unavailable. Please retry.") from last_err


# ── Convenience builders ───────────────────────────────────────────────────────
def system_user(system: str, user: str) -> List[Dict[str, str]]:
    """Build standard [system, user] message list."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ── Token usage logger ─────────────────────────────────────────────────────────
_usage_lock = Lock()
_total_prompt_tokens: int = 0
_total_completion_tokens: int = 0


def _log_usage(response, sync: bool = True):
    global _total_prompt_tokens, _total_completion_tokens
    try:
        usage = response.usage
        if usage:
            with _usage_lock:
                _total_prompt_tokens += usage.prompt_tokens
                _total_completion_tokens += usage.completion_tokens
    except Exception:
        pass


def get_token_usage() -> Dict[str, int]:
    """Return cumulative token usage for this server session."""
    with _usage_lock:
        return {
            "prompt_tokens": _total_prompt_tokens,
            "completion_tokens": _total_completion_tokens,
            "total_tokens": _total_prompt_tokens + _total_completion_tokens,
        }
