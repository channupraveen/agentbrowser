"""MCP server: lets Claude (or any MCP client) drive agentbrowser directly.

The AI client is the brain; this server is the hands. No separate LLM API key is
needed. Every tool returns compact text, so pages cost few tokens.

Run:  python -m agentbrowser.mcp_server        (stdio transport)
Env:  AGENTBROWSER_DATA      profile, skills and API catalog folder (default .agentbrowser)
      AGENTBROWSER_HEADLESS  "0" to show the Chromium window (default hidden)
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .browser import AgentBrowser, to_compact

mcp = FastMCP(
    "agentbrowser",
    instructions=(
        "A fast browser for AI agents, running a local Chromium. Pages come back as compact text: "
        "a list of interactive elements with refs (e1, e2...) plus the page text. Act on elements by "
        "ref. Prefer `read` for just reading a page (plain HTTP, no browser). Use `act` to send several "
        "actions in one call. Before repeating a task, check `list_skills`: replaying a saved skill "
        "needs no reasoning and is much faster. Record new repeatable tasks with `record_start`/`record_stop`."
    ),
)

_browser: AgentBrowser | None = None
_lock = asyncio.Lock()


async def browser() -> AgentBrowser:
    global _browser
    async with _lock:
        if _browser is None:
            _browser = await AgentBrowser(
                data_dir=os.getenv("AGENTBROWSER_DATA", ".agentbrowser"),
                headless=os.getenv("AGENTBROWSER_HEADLESS", "1") != "0",
            ).start()
        return _browser


def _page(snap: dict | None) -> str:
    return to_compact(snap) if snap else ""


@mcp.tool()
async def read(url: str, max_text: int = 8000) -> str:
    """Read a page as text, as fast as possible. Tries plain HTTP first and only uses the
    browser for JavaScript-rendered pages. Read-only: use `open` if you need to click or type."""
    b = await browser()
    r = await b.read(url, max_text=max_text)
    head = f"[{r.get('via')} · {r.get('ms')} ms]"
    if r.get("via") == "browser":
        return f"{head}\n{to_compact(r)}"
    links = "\n".join(f"- {l['text']} -> {l['href']}" for l in r.get("links", [])[:60])
    return f"{head}\n{r.get('title', '')}\n{r.get('url', '')}\n\ntext:\n{r['text']}\n\nlinks:\n{links}"


@mcp.tool()
async def open(url: str, tab: str = "main") -> str:
    """Open a URL in the browser and return the page: interactive elements with refs and the text."""
    b = await browser()
    await b.act({"action": "goto", "url": url}, tab=tab)
    return _page(await b.snapshot(tab))


@mcp.tool()
async def snapshot(tab: str = "main", diff: bool = False) -> str:
    """Return the current page. With diff=true, only elements and text that changed since the last snapshot."""
    b = await browser()
    return _page(await b.snapshot(tab, diff=diff))


@mcp.tool()
async def act(actions: list[dict[str, Any]], tab: str = "main") -> str:
    """Run one or more actions in order, then return what changed on the page.

    Each action is an object, e.g.
      {"action": "click", "ref": "e3"}
      {"action": "type", "ref": "e5", "text": "hello"}
      {"action": "press", "key": "Enter"}
      {"action": "select", "ref": "e7", "value": "UK"}
      {"action": "goto", "url": "https://..."}
      {"action": "scroll", "dy": 800}, {"action": "wait_for", "text": "Done"}, {"action": "back"},
      {"action": "check", "ref": "e9"}, {"action": "uncheck", "ref": "e9"}
    Batch whole forms into one call. Stops at the first failing action."""
    b = await browser()
    r = await b.act_batch(actions, tab=tab)
    if r["ok"]:
        return f"ok ({len(r['results'])} actions)\n\n{_page(r['snapshot'])}"
    err = r["results"][-1].get("error", "")
    return f"failed at action {r['failed_at']}: {err}\n\ncurrent page:\n{_page(r['snapshot'])}"


@mcp.tool()
async def record_start(name: str, tab: str = "main") -> str:
    """Start recording the actions you take as a reusable skill (starting from the current page)."""
    b = await browser()
    r = await b.record_start(name, tab=tab)
    return f"recording '{name}' from {r['start_url'] or '(blank page)'}"


@mcp.tool()
async def record_stop(params: dict[str, str] | None = None, description: str = "") -> str:
    """Stop recording and save the skill. `params` maps a parameter name to a literal value you typed,
    so it can be replaced on replay, e.g. {"email": "me@x.com"}. Password fields are never stored."""
    b = await browser()
    s = await b.record_stop(params or {}, description)
    return f"saved skill '{s['name']}' with {len(s['steps'])} steps; params: {s['params'] or 'none'}"


@mcp.tool()
async def list_skills() -> str:
    """List saved skills (recorded tasks that can be replayed without any reasoning)."""
    b = await browser()
    skills = b.skills.list()
    if not skills:
        return "no skills saved yet"
    return "\n".join(f"- {s['name']}: {s['steps']} steps; params {s['params'] or 'none'}"
                     f"{' - ' + s['description'] if s['description'] else ''}" for s in skills)


@mcp.tool()
async def replay(name: str, params: dict[str, str] | None = None, tab: str = "main") -> str:
    """Replay a saved skill directly, with no reasoning needed. If the site changed and a step fails,
    you get the current page so you can continue by hand from that step."""
    b = await browser()
    try:
        r = await b.replay(name, params or {}, tab=tab)
    except KeyError as e:
        return f"error: {e}"
    if r["ok"]:
        return f"replayed '{name}': {r['steps']} steps in {r['ms']} ms\n\n{_page(await b.snapshot(tab))}"
    return (f"replay of '{name}' failed at step {r['failed_step']} ({r['step']['action']}): {r['error']}\n"
            f"continue from here:\n{_page(r['snapshot'])}")


@mcp.tool()
async def list_apis(host: str | None = None) -> str:
    """List JSON APIs discovered while browsing (method, path, params, response shape).
    Calling these with `call_api` is much faster than clicking through the UI."""
    b = await browser()
    eps = b.list_apis(host)
    if not eps:
        return "no APIs discovered yet; browse a site that loads data dynamically first"
    return "\n".join(f"- {e['method']} {e['example_url']}  query={e['query_params']}  "
                     f"returns={json.dumps(e['response_shape'])[:200]}" for e in eps)


@mcp.tool()
async def call_api(url: str, method: str = "GET", params: dict[str, Any] | None = None,
                   json_body: Any = None) -> str:
    """Call an HTTP endpoint directly using the browser's cookies (e.g. one found by `list_apis`)."""
    b = await browser()
    r = await b.call_api(method, url, params=params, json=json_body)
    body = r["body"] if isinstance(r["body"], str) else json.dumps(r["body"])
    return f"status {r['status']} in {r['ms']} ms\n{body[:6000]}"


def _serve_http(port: int) -> None:
    """Serve over Streamable HTTP so it can be added as a remote/custom connector.

    The endpoint lives under a secret path (/<token>/mcp): anyone without the token gets 404.
    Put it behind an HTTPS tunnel (e.g. `cloudflared tunnel --url http://localhost:<port>`)
    and add https://<tunnel-host>/<token>/mcp as a custom connector in Claude.
    """
    import secrets
    from pathlib import Path

    from mcp.server.transport_security import TransportSecuritySettings

    data = Path(os.getenv("AGENTBROWSER_DATA", ".agentbrowser"))
    data.mkdir(parents=True, exist_ok=True)
    token_file = data / "mcp_token.txt"
    token = os.getenv("AGENTBROWSER_MCP_TOKEN") or (
        token_file.read_text().strip() if token_file.exists() else "")
    if not token:
        token = secrets.token_urlsafe(24)
        token_file.write_text(token)

    mcp.settings.host = "127.0.0.1"  # only reachable through your tunnel, never your LAN
    mcp.settings.port = port
    mcp.settings.streamable_http_path = f"/{token}/mcp"
    # Requests arrive via the tunnel with its public Host header; the secret path is the guard.
    mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    print(f"agentbrowser MCP (HTTP) listening on http://127.0.0.1:{port}")
    print(f"Connector path: /{token}/mcp")
    print(f"Add as a custom connector:  https://<your-tunnel-host>/{token}/mcp")
    print(f"(token saved in {token_file}; keep it secret)", flush=True)
    mcp.run(transport="streamable-http")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="agentbrowser-mcp")
    ap.add_argument("--http", action="store_true", help="serve over HTTP for remote connectors")
    ap.add_argument("--port", type=int, default=int(os.getenv("AGENTBROWSER_MCP_PORT", "8790")))
    args = ap.parse_args()
    if args.http:
        _serve_http(args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
