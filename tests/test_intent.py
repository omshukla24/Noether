import json

import httpx
import pytest

from noether.intent import detect_dep_bumps, read_intent, tavily_notes
from noether.model import Change, ChangedFile, DepBump
from noether.nemotron import ModelError


def pkg(**sections):
    return json.dumps(sections)


def pkg_change(base, head, path="package.json"):
    return Change("a/b", "main", "pr", files=[ChangedFile(path, "modified", [], base, head)])


def test_detects_bumps_in_all_dependency_sections():
    change = pkg_change(
        pkg(dependencies={"left-pad": "1.0.0", "same": "2.0.0", "gone": "1.0.0"}, devDependencies={"vite": "^5.0.0"}),
        pkg(dependencies={"left-pad": "1.3.0", "same": "2.0.0", "added": "1.0.0"}, devDependencies={"vite": "^6.0.0"},
            peerDependencies={"react": "18"}))
    assert [(b.name, b.old, b.new) for b in detect_dep_bumps(change)] == [
        ("left-pad", "1.0.0", "1.3.0"), ("vite", "^5.0.0", "^6.0.0")]


def test_nested_package_json_counts_and_other_files_do_not():
    assert len(detect_dep_bumps(pkg_change(pkg(dependencies={"a": "1"}), pkg(dependencies={"a": "2"}), "web/package.json"))) == 1
    assert detect_dep_bumps(pkg_change(pkg(dependencies={"a": "1"}), pkg(dependencies={"a": "2"}), "notpackage.json")) == []


def test_unreadable_or_missing_package_json_means_no_bumps():
    assert detect_dep_bumps(pkg_change("{broken", pkg(dependencies={"a": "2"}))) == []
    assert detect_dep_bumps(pkg_change(None, pkg(dependencies={"a": "2"}))) == []
    assert detect_dep_bumps(pkg_change("[1]", "[2]")) == []
    assert detect_dep_bumps(Change("a/b", "main", "pr")) == []


def tavily_http(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tavily_notes_sends_the_documented_request_and_formats_results():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        results = [{"title": f"T{i}", "content": "line one\n  line two", "url": f"https://x/{i}"} for i in range(7)]
        return httpx.Response(200, json={"results": results})

    notes = tavily_notes(DepBump("vite", "5.0.0", "6.0.0"), "tvly-key", tavily_http(handler))
    assert seen["url"] == "https://api.tavily.com/search" and seen["auth"] == "Bearer tvly-key"
    assert seen["body"] == {"query": "vite 6.0.0 changelog breaking changes", "max_results": 5, "search_depth": "basic"}
    assert len(notes) == 5 and notes[0] == "T0: line one line two (https://x/0)"


def test_tavily_skips_odd_results_and_closes_a_client_it_opened(monkeypatch):
    opened = []
    real_client = httpx.Client  # the patch below replaces httpx.Client everywhere

    def fake_client(timeout):
        handler = lambda r: httpx.Response(200, json={"results": ["odd", {"title": "ok", "content": "c", "url": "u"}]})
        opened.append(real_client(transport=httpx.MockTransport(handler)))
        return opened[-1]

    monkeypatch.setattr("noether.intent.httpx.Client", fake_client)
    assert tavily_notes(DepBump("a", "1", "2"), "k") == ["ok: c (u)"]
    assert opened[0].is_closed


@pytest.mark.parametrize("make", [
    lambda r: httpx.Response(500),
    lambda r: httpx.Response(401, json={"detail": "bad key"}),
    lambda r: httpx.Response(200, text="not json"),
    lambda r: httpx.Response(200, json=["unexpected"]),
])
def test_tavily_failures_return_nothing(make):
    assert tavily_notes(DepBump("a", "1", "2"), "k", tavily_http(make)) == []


def test_tavily_network_error_returns_nothing():
    def boom(request):
        raise httpx.ConnectError("down")

    assert tavily_notes(DepBump("a", "1", "2"), "k", tavily_http(boom)) == []


def intent_reply(make_client, **over):
    data = {"summary": "Renames the tax helper.", "intended_changes": ["taxFor now takes the region first"]}
    data.update(over)
    return make_client(make_client.ok(json.dumps(data)))


def test_read_intent_uses_nano_without_thinking(make_client, change):
    client = intent_reply(make_client)
    intent = read_intent(client, change)
    assert intent.summary == "Renames the tax helper."
    assert intent.intended_changes == ["taxFor now takes the region first"]
    assert intent.dependency_bumps == []
    sent = client.sent[0]
    assert sent["model"] == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}
    user = sent["messages"][-1]["content"]
    assert "Tidy clamp" in user and "Small cleanup." in user and "hi - 1" in user  # title, body, diff


def test_read_intent_attaches_bumps_and_tavily_notes(make_client, change):
    change.files.append(ChangedFile("package.json", "modified", [], pkg(dependencies={"vite": "5.0.0"}),
                                    pkg(dependencies={"vite": "6.0.0"})))
    http = tavily_http(lambda r: httpx.Response(200, json={"results": [{"title": "v6", "content": "drops node 16",
                                                                         "url": "https://x"}]}))
    client = intent_reply(make_client, intended_changes=["vite 6 is now used"])
    intent = read_intent(client, change, tavily_key="tvly", http=http)
    assert [(b.name, b.old, b.new) for b in intent.dependency_bumps] == [("vite", "5.0.0", "6.0.0")]
    assert intent.dependency_bumps[0].notes == ["v6: drops node 16 (https://x)"]
    assert "drops node 16" in client.sent[0]["messages"][-1]["content"]


def test_without_a_tavily_key_nothing_is_searched(make_client, change):
    change.files.append(ChangedFile("package.json", "modified", [], pkg(dependencies={"vite": "5"}), pkg(dependencies={"vite": "6"})))

    def forbidden(request):
        raise AssertionError("no search without a key")

    intent = read_intent(intent_reply(make_client), change, http=tavily_http(forbidden))
    assert intent.dependency_bumps[0].notes == []


def test_a_pr_with_no_announced_change_gives_an_empty_list(make_client, change):
    intent = read_intent(intent_reply(make_client, intended_changes=["  ", ""]), change)
    assert intent.intended_changes == []


def test_model_failure_propagates(make_client, change):
    client = make_client(make_client.ok("no json at all"), make_client.ok("still none"))
    with pytest.raises(ModelError):
        read_intent(client, change)
