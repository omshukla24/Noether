"""Token Factory client for the Nemotron models: one chat call, budgets, retries, JSON replies.

Plain httpx, no vendor SDK. Every call is recorded as a ModelCall and counted against a per-run token cap.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx
import jsonschema
from dotenv import load_dotenv

from noether.model import ModelCall

# Exact ids from GET /v1/models. The casing is inconsistent on purpose; never "fix" it.
MODELS = {
    "intent": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "summary": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "pin": "nvidia/nemotron-3-super-120b-a12b",
    "judge": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "locate": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "fix": "nvidia/Nemotron-3-Ultra-550b-a55b",
}
FALLBACK = {
    "intent": "nvidia/Nemotron-3_5-Lightning",
    "summary": "nvidia/Nemotron-3_5-Lightning",
}
# Reasoning tokens count against max_tokens, so these are generous.
DEFAULT_BUDGET = {"intent": 4000, "summary": 2000, "pin": 16000, "judge": 6000, "locate": 6000, "fix": 12000}

# Live check 2026-10-27: chat_template_kwargs {"enable_thinking": false} drops reasoning to 0 tokens on Nano, Super
# and Ultra; "/no_think" and reasoning_effort did nothing. Only plain reading tasks go without thinking; the judge
# and the fixer keep it because a wrong "intended" or a wrong edit costs more than the tokens.
# pin: the sandbox throws out wrong tests, so speed beats deliberation there (thinking made it ~200 s)
NO_THINKING_ROLES = frozenset({"intent", "summary", "pin"})

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
RETRY_BACKOFF = (1.0, 3.0)  # seconds before retry 1 and 2


class ModelError(RuntimeError):
    """A model call failed or its reply was unusable."""


class BudgetExhausted(ModelError):
    """The reply was empty or cut off: reasoning used the whole token budget."""


class TokenCapHit(ModelError):
    """The run already spent its token cap."""


@dataclass
class Reply:
    text: str
    model: str
    usage: dict
    ms: float


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)


def strip_thinking(text: str) -> str:
    """Drop <think> sections. Token Factory normally puts reasoning in a separate message field; this covers
    models that leak it into the content."""
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text:  # the chat template opened the tag, so only the closing one shows
        text = text.rsplit("</think>", 1)[1]
    elif "<think>" in text:  # cut off in the middle of a thought
        text = text.split("<think>", 1)[0]
    return text.strip()


def extract_json(text: str) -> dict | list:
    """First JSON object or array in a reply, whatever fences or prose surround it."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                return decoder.raw_decode(text, i)[0]
            except ValueError:
                continue
    raise ModelError(f"no JSON found in the reply: {text[:120]!r}")


def _with_schema(messages: list[dict], schema: dict) -> list[dict]:
    """Copy of messages whose system prompt also states the schema (used when the server only does json_object)."""
    note = ("Reply with one JSON value only, no prose and no code fences, matching this JSON schema:\n"
            + json.dumps(schema))
    out = [dict(m) for m in messages]
    if out and out[0]["role"] == "system":
        out[0]["content"] = out[0]["content"] + "\n\n" + note
        return out
    return [{"role": "system", "content": note}] + out


class Client:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 transport: httpx.BaseTransport | None = None, max_run_tokens: int = 250_000,
                 timeout: float = 180.0):
        if not api_key:
            raise ModelError("NEBIUS_API_KEY is not set")
        self._http = httpx.Client(base_url=base_url.rstrip("/") + "/", transport=transport, timeout=timeout,
                                  headers={"Authorization": f"Bearer {api_key}"})
        self.max_run_tokens = max_run_tokens
        self.calls: list[ModelCall] = []
        self.tokens_used = 0
        self.sleep: Callable[[float], None] = time.sleep  # tests replace it

    @classmethod
    def from_env(cls, env_file: str | None = None, **kw: Any) -> "Client":
        path = env_file or (".env.local" if Path(".env.local").exists() else None)
        if path:
            load_dotenv(path)
        if "max_run_tokens" not in kw and os.environ.get("NOETHER_MAX_TOKENS"):
            kw["max_run_tokens"] = int(os.environ["NOETHER_MAX_TOKENS"])
        base_url = os.environ.get("NEBIUS_BASE_URL") or DEFAULT_BASE_URL
        return cls(os.environ.get("NEBIUS_API_KEY", ""), base_url=base_url, **kw)

    def chat(self, role: str, messages: list[dict], max_tokens: int | None = None,
             json_schema: dict | None = None, temperature: float = 0.2) -> Reply:
        if role not in MODELS:
            raise ModelError(f"unknown model role {role!r}")
        try:
            return self._chat_with_budget(role, MODELS[role], messages, max_tokens, json_schema, temperature)
        except (TokenCapHit, BudgetExhausted):
            raise
        except ModelError:
            if role not in FALLBACK:
                raise
            return self._chat_with_budget(role, FALLBACK[role], messages, max_tokens, json_schema, temperature)

    def chat_json(self, role: str, messages: list[dict], schema: dict, max_tokens: int | None = None) -> dict | list:
        """chat + extract_json + schema check, with one repair round that shows the model what was wrong."""
        msgs = _with_schema(messages, schema)
        problem = ""
        for _ in range(2):
            reply = self.chat(role, msgs, max_tokens, json_schema=schema)
            try:
                value = extract_json(reply.text)
                jsonschema.validate(value, schema)
                return value
            except (ModelError, jsonschema.ValidationError) as e:
                problem = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
                problem = problem[:300]
                msgs = msgs + [{"role": "assistant", "content": reply.text},
                               {"role": "user", "content": f"That reply was rejected: {problem}\n"
                                                           "Send the corrected JSON only."}]
        raise ModelError(f"{role}: the reply was still not valid after one repair: {problem}")

    def _chat_with_budget(self, role, model, messages, max_tokens, json_schema, temperature) -> Reply:
        default = DEFAULT_BUDGET[role]
        budget = max_tokens or default
        try:
            return self._complete(role, model, messages, budget, json_schema, temperature)
        except BudgetExhausted:
            retry = min(budget * 2, default * 2)
            if retry <= budget:
                raise
        return self._complete(role, model, messages, retry, json_schema, temperature)

    def _complete(self, role, model, messages, budget, json_schema, temperature) -> Reply:
        if self.tokens_used >= self.max_run_tokens:
            raise TokenCapHit(f"token cap of {self.max_run_tokens} reached ({self.tokens_used} used)")
        body: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": budget,
                                "temperature": temperature}
        if role in NO_THINKING_ROLES and model == MODELS[role]:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "reply", "strict": True, "schema": json_schema}}
        start = time.perf_counter()
        resp = self._post(body)
        if resp.status_code == 400 and json_schema is not None:
            body["response_format"] = {"type": "json_object"}  # the server refused the schema form
            resp = self._post(body)
        ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            raise ModelError(f"Token Factory answered HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
            choice = data["choices"][0]
            text = strip_thinking(choice["message"].get("content") or "")
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
            raise ModelError(f"unexpected Token Factory reply shape: {type(e).__name__}") from e
        tokens_in = int(usage.get("prompt_tokens") or 0)
        tokens_out = int(usage.get("completion_tokens") or 0)
        self.tokens_used += int(usage.get("total_tokens") or tokens_in + tokens_out)
        self.calls.append(ModelCall(role, model, tokens_in, tokens_out, round(ms, 1)))
        # A cut-off JSON reply is as useless as an empty one.
        if not text or (json_schema is not None and choice.get("finish_reason") == "length"):
            raise BudgetExhausted(f"{role}: no usable reply within {budget} tokens")
        return Reply(text, model, usage, ms)

    def _post(self, body: dict) -> httpx.Response:
        problem = ""
        for attempt in range(len(RETRY_BACKOFF) + 1):
            if attempt:
                self.sleep(RETRY_BACKOFF[attempt - 1])
            try:
                resp = self._http.post("chat/completions", json=body)
            except httpx.TransportError as e:
                problem = type(e).__name__
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                problem = f"HTTP {resp.status_code}"
                continue
            return resp
        raise ModelError(f"Token Factory unavailable after {len(RETRY_BACKOFF) + 1} tries: {problem}")
