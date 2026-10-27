"""Live Token Factory checks (about 5 tiny calls). Run with NOETHER_LIVE=1; the key comes from the environment,
from NOETHER_ENV_FILE, or from .env.local in the working directory."""
import json
import os

import jsonschema
import pytest

from noether.nemotron import FALLBACK, MODELS, Client

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("NOETHER_LIVE") != "1", reason="set NOETHER_LIVE=1 to call Token Factory")]

PICK = {"type": "object", "properties": {"color": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["color", "n"], "additionalProperties": False}
ASK = [{"role": "user", "content": "Pick a favourite color and a lucky number."}]  # does not mention JSON on purpose


@pytest.fixture(scope="module")
def client():
    return Client.from_env(os.environ.get("NOETHER_ENV_FILE"))


@pytest.mark.parametrize("role", ["intent", "pin", "judge"])
def test_json_schema_mode_is_honoured(client, role):
    # The prompt never asks for JSON, so a valid object can only come from the response_format.
    reply = client.chat(role, ASK, max_tokens=1500, json_schema=PICK)
    assert reply.model == MODELS[role]
    jsonschema.validate(json.loads(reply.text), PICK)


def test_thinking_is_off_for_the_intent_role(client):
    before = len(client.calls)
    client.chat("intent", [{"role": "user", "content": "Return JSON with color=blue and n=3."}], max_tokens=1500)
    assert client.calls[before].tokens_out < 60  # about 77 with thinking, 17 without (2026-10-27)


def test_lightning_keeps_its_thinking_out_of_the_content(client):
    body = {"model": FALLBACK["intent"], "max_tokens": 1500,
            "messages": [{"role": "user", "content": "Return JSON with color=blue and n=3."}]}
    message = client._http.post("chat/completions", json=body).json()["choices"][0]["message"]
    assert message["reasoning_content"] and "<think>" not in message["content"]
    assert message["content"].strip().startswith("{")
