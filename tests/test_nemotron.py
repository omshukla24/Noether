import os

import httpx
import pytest

from noether.nemotron import (DEFAULT_BUDGET, FALLBACK, MODELS, BudgetExhausted, Client, ModelError, TokenCapHit,
                              extract_json, strip_thinking)

SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}


def test_model_ids_are_exact():
    assert MODELS["pin"] == "nvidia/nemotron-3-super-120b-a12b"
    assert MODELS["judge"] == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert MODELS["intent"] == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert FALLBACK["intent"] == "nvidia/Nemotron-3_5-Lightning"
    assert set(DEFAULT_BUDGET) == set(MODELS)


def test_chat_returns_text_and_records_the_call(make_client):
    seen = {}

    def reply(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return make_client.ok("hello", total=120)

    client = make_client(reply)
    out = client.chat("judge", [{"role": "user", "content": "hi"}])
    assert out.text == "hello" and out.model == MODELS["judge"] and out.usage["total_tokens"] == 120
    assert seen["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert client.tokens_used == 120
    call = client.calls[0]
    assert (call.role, call.model, call.tokens_in, call.tokens_out) == ("judge", MODELS["judge"], 110, 10)
    assert client.sent[0]["max_tokens"] == DEFAULT_BUDGET["judge"]


def test_thinking_is_off_for_reading_and_pinning_but_on_for_judging(make_client):
    client = make_client(make_client.ok("a"), make_client.ok("b"), make_client.ok("c"))
    client.chat("intent", [{"role": "user", "content": "x"}])
    client.chat("pin", [{"role": "user", "content": "x"}])
    client.chat("judge", [{"role": "user", "content": "x"}])
    assert client.sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert client.sent[1]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in client.sent[2]


def test_empty_content_retries_once_with_double_budget(make_client):
    client = make_client(make_client.ok(None, finish="length"), make_client.ok("done"))
    assert client.chat("pin", [{"role": "user", "content": "x"}]).text == "done"
    assert [s["max_tokens"] for s in client.sent] == [16000, 32000]
    assert len(client.calls) == 2  # the empty call still cost tokens


def test_empty_content_twice_is_budget_exhausted(make_client):
    client = make_client(make_client.ok(""), make_client.ok(None))
    with pytest.raises(BudgetExhausted):
        client.chat("judge", [{"role": "user", "content": "x"}])
    assert len(client.sent) == 2


def test_budget_retry_is_capped_at_twice_the_default(make_client):
    client = make_client(make_client.ok(None))
    with pytest.raises(BudgetExhausted):
        client.chat("judge", [{"role": "user", "content": "x"}], max_tokens=2 * DEFAULT_BUDGET["judge"])
    assert len(client.sent) == 1


def test_cut_off_json_counts_as_exhausted(make_client):
    client = make_client(make_client.ok('{"n": ', finish="length"), make_client.ok('{"n": 1}'))
    assert client.chat("judge", [{"role": "user", "content": "x"}], json_schema=SCHEMA).text == '{"n": 1}'


def test_thinking_text_is_stripped_from_the_reply(make_client):
    client = make_client(make_client.ok("<think>let me see {\"n\": 9}</think>\n{\"n\": 2}"))
    assert client.chat("judge", [{"role": "user", "content": "x"}]).text == '{"n": 2}'


@pytest.mark.parametrize("raw,clean", [
    ("<think>a</think>answer", "answer"),
    ("reasoning only</think>answer", "answer"),
    ("answer<think>cut off", "answer"),
    ("<think>a</think>x<think>b</think>y", "xy"),
    ("  plain  ", "plain"),
])
def test_strip_thinking(raw, clean):
    assert strip_thinking(raw) == clean


def test_retries_429_then_succeeds(make_client):
    client = make_client(httpx.Response(429), make_client.ok("ok"))
    slept = []
    client.sleep = slept.append
    assert client.chat("judge", [{"role": "user", "content": "x"}]).text == "ok"
    assert slept == [1.0]


def test_retries_500_twice_then_succeeds(make_client):
    client = make_client(httpx.Response(500), httpx.Response(503), make_client.ok("ok"))
    slept = []
    client.sleep = slept.append
    assert client.chat("pin", [{"role": "user", "content": "x"}]).text == "ok"
    assert slept == [1.0, 3.0]


def test_gives_up_after_three_server_errors(make_client):
    client = make_client(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    with pytest.raises(ModelError, match="unavailable"):
        client.chat("pin", [{"role": "user", "content": "x"}])
    assert client.calls == []


def test_network_errors_are_retried(make_client):
    def boom(request):
        raise httpx.ConnectError("down")

    client = make_client(boom, make_client.ok("back"))
    assert client.chat("judge", [{"role": "user", "content": "x"}]).text == "back"


def test_client_errors_are_not_retried(make_client):
    client = make_client(httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(ModelError, match="HTTP 401"):
        client.chat("judge", [{"role": "user", "content": "x"}])
    assert len(client.sent) == 1


def test_schema_request_falls_back_to_json_object_on_400(make_client):
    client = make_client(httpx.Response(400, json={"error": "unsupported schema"}), make_client.ok('{"n": 1}'))
    client.chat("judge", [{"role": "user", "content": "x"}], json_schema=SCHEMA)
    assert client.sent[0]["response_format"]["type"] == "json_schema"
    assert client.sent[1]["response_format"] == {"type": "json_object"}


def test_token_cap_stops_before_the_call(make_client):
    client = make_client(make_client.ok("one", total=300), make_client.ok("two"), max_run_tokens=250)
    client.chat("judge", [{"role": "user", "content": "x"}])
    with pytest.raises(TokenCapHit):
        client.chat("judge", [{"role": "user", "content": "x"}])
    assert len(client.sent) == 1


def test_light_roles_fall_back_to_lightning(make_client):
    client = make_client(httpx.Response(500), httpx.Response(500), httpx.Response(500), make_client.ok("fallback"))
    out = client.chat("intent", [{"role": "user", "content": "x"}])
    assert out.text == "fallback" and out.model == FALLBACK["intent"]
    assert client.sent[-1]["model"] == FALLBACK["intent"]
    assert "chat_template_kwargs" not in client.sent[-1]  # untested on Lightning, so not sent


def test_heavy_roles_do_not_fall_back(make_client):
    client = make_client(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    with pytest.raises(ModelError):
        client.chat("pin", [{"role": "user", "content": "x"}])


def test_odd_reply_shape_is_a_model_error(make_client):
    client = make_client(httpx.Response(200, json={"choices": []}))
    with pytest.raises(ModelError, match="shape"):
        client.chat("judge", [{"role": "user", "content": "x"}])


def test_unknown_role_and_missing_key():
    with pytest.raises(ModelError, match="NEBIUS_API_KEY"):
        Client("")
    client = Client("k", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(ModelError, match="unknown model role"):
        client.chat("poet", [])


def test_from_env_reads_the_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", {})  # load_dotenv writes into it; the real environment stays clean
    env = tmp_path / ".env.local"
    env.write_text("NEBIUS_API_KEY=abc\nNEBIUS_BASE_URL=https://example.test/v1\nNOETHER_MAX_TOKENS=1234\n")
    client = Client.from_env(str(env))
    assert client.max_run_tokens == 1234
    assert str(client._http.base_url) == "https://example.test/v1/"
    assert client._http.headers["authorization"] == "Bearer abc"


# --- extract_json -----------------------------------------------------------------------------------------

def test_extract_json_reads_fenced_blocks_and_prose():
    assert extract_json('Sure!\n```json\n{"a": [1, 2]}\n```\nDone.') == {"a": [1, 2]}
    assert extract_json("The list is [1, 2, 3].") == [1, 2, 3]
    assert extract_json('use {name} like so: {"ok": true}') == {"ok": True}
    assert extract_json('{"code": "if (a) { b(); }"}') == {"code": "if (a) { b(); }"}


def test_extract_json_raises_when_there_is_none():
    with pytest.raises(ModelError):
        extract_json("no braces here")
    with pytest.raises(ModelError):
        extract_json("{broken")


# --- chat_json --------------------------------------------------------------------------------------------

def test_chat_json_returns_the_validated_value_and_sends_the_schema(make_client):
    client = make_client(make_client.ok('```json\n{"n": 3}\n```'))
    assert client.chat_json("judge", [{"role": "user", "content": "x"}], SCHEMA) == {"n": 3}
    sent = client.sent[0]
    assert sent["messages"][0]["role"] == "system" and '"required"' in sent["messages"][0]["content"]
    assert sent["response_format"]["type"] == "json_schema"


def test_chat_json_appends_the_schema_to_an_existing_system_prompt(make_client):
    client = make_client(make_client.ok('{"n": 1}'))
    messages = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "x"}]
    client.chat_json("judge", messages, SCHEMA)
    assert [m["role"] for m in client.sent[0]["messages"]] == ["system", "user"]
    assert client.sent[0]["messages"][0]["content"].startswith("Be brief.")
    assert messages[0]["content"] == "Be brief."  # the caller's list is untouched


def test_chat_json_repairs_once_with_the_error(make_client):
    client = make_client(make_client.ok("not json"), make_client.ok('{"n": "wrong type"}'))
    with pytest.raises(ModelError, match="after one repair"):
        client.chat_json("judge", [{"role": "user", "content": "x"}], SCHEMA)
    assert len(client.sent) == 2
    assert "rejected" in client.sent[1]["messages"][-1]["content"]


def test_chat_json_repair_can_succeed(make_client):
    client = make_client(make_client.ok('{"n": "one"}'), make_client.ok('{"n": 1}'))
    assert client.chat_json("judge", [{"role": "user", "content": "x"}], SCHEMA) == {"n": 1}
    assert "'one' is not of type 'integer'" in client.sent[1]["messages"][-1]["content"]
