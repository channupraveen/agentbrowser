import asyncio
import json

import pytest

from agentbrowser import AgentBrowser
from tests.demo_site import serve


@pytest.fixture(scope="module")
def site():
    server, url = serve()
    yield url
    server.shutdown()


def run(coro):
    return asyncio.run(coro)


def ref_for(snap, name):
    return next(e["ref"] for e in snap["elements"] if e["name"] == name)


def test_fast_read_skips_browser_for_static_html(site, tmp_path):
    async def go():
        async with AgentBrowser(tmp_path) as b:
            static = await b.read(f"{site}/article")
            spa = await b.read(f"{site}/spa")
            return static, spa

    static, spa = run(go())
    assert static["via"] == "http" and "plain HTML" in static["text"]
    assert spa["via"] == "browser" and "Rendered by JS" in spa["text"]


def test_record_replay_and_api_discovery(site, tmp_path):
    async def go():
        async with AgentBrowser(tmp_path) as b:
            await b.act({"action": "goto", "url": f"{site}/"})
            snap = await b.snapshot()
            assert snap["title"] == "Shop login"

            await b.record_start("login and load orders")
            r = await b.act_batch([
                {"action": "type", "ref": ref_for(snap, "Email"), "text": "channu@example.com"},
                {"action": "type", "ref": ref_for(snap, "Password"), "text": "hunter2"},
                {"action": "click", "ref": ref_for(snap, "Sign in")},
            ])
            assert r["ok"], r
            dash = await b.snapshot()
            assert "Signed in as channu@example.com" in dash["text"]
            await b.act({"action": "click", "ref": ref_for(dash, "Load orders")})
            await b.act({"action": "wait_for", "text": "Rice 5kg"})
            diff = await b.snapshot(diff=True)
            assert diff["diff"] and "Rice 5kg" in diff["text"]
            skill = await b.record_stop(params={"email": "channu@example.com"}, description="demo")

            # Secrets never hit disk; the typed email became a parameter.
            saved = (tmp_path / "skills" / "login-and-load-orders.json").read_text()
            assert "hunter2" not in saved
            assert skill["params"] == ["email", "password"]

            # Replay in a fresh tab: no LLM, no refs, just stable locators.
            result = await b.replay("login and load orders",
                                    {"email": "vishnu@example.com", "password": "x"}, tab="t2")
            assert result["ok"] and result["llm_calls"] == 0, result
            after = await b.snapshot(tab="t2")
            assert "Signed in as vishnu@example.com" in after["text"]
            assert "Rice 5kg" in after["text"]

            # The orders endpoint was discovered while browsing...
            apis = b.list_apis("127.0.0.1")
            ep = next(e for e in apis if e["path"] == "/api/users/{id}/orders")
            assert ep["method"] == "GET" and ep["query_params"] == ["status"]
            # ...and can now be called directly, skipping the UI.
            direct = await b.call_api("GET", f"{site}/api/users/42/orders", params={"status": "open"})
            assert direct["status"] == 200 and direct["body"]["orders"][0]["item"] == "Rice 5kg"
            return result, direct

    result, direct = run(go())
    print(f"\nreplay: {result['ms']} ms for {result['steps']} steps; direct API call: {direct['ms']} ms")


def test_replay_hands_back_to_agent_when_site_changes(site, tmp_path):
    async def go():
        async with AgentBrowser(tmp_path, action_timeout_ms=800) as b:
            await b.act({"action": "goto", "url": f"{site}/"})
            snap = await b.snapshot()
            await b.record_start("broken")
            await b.act({"action": "click", "ref": ref_for(snap, "Sign in")})
            await b.record_stop()
            path = tmp_path / "skills" / "broken.json"
            skill = json.loads(path.read_text())
            skill["steps"][0]["target"] = {"tag": "button", "id": "gone", "css": "#gone"}
            path.write_text(json.dumps(skill))
            return await b.replay("broken")

    result = run(go())
    assert not result["ok"] and result["failed_step"] == 0
    assert result["snapshot"]["title"] == "Shop login"
