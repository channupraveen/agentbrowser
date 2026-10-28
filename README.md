# agentbrowser

**A fast browser for AI agents. The first run uses AI; every run after is instant.**

[![Tests](https://github.com/channupraveen/agentbrowser/actions/workflows/tests.yml/badge.svg)](https://github.com/channupraveen/agentbrowser/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

Most AI browser agents are slow for the same reason: every step is *screenshot → vision model → guess where to click → screenshot again*. agentbrowser gives the AI a **text view** of the web instead, lets it act on elements by reference, and then takes the AI out of the loop wherever it can.

It works with **Claude through MCP** (no separate AI account or API key), and with any other agent through an HTTP API or Python.

## Why it's faster

| | Typical agent browser | agentbrowser |
|---|---|---|
| What the AI reads | Screenshots | Compact text with element refs (a login page is ~34 tokens) |
| How it clicks | Guesses coordinates | `click e11`, an exact element reference |
| Follow-up steps | Whole page again | Only what changed (diff) |
| Several actions | One round trip each | Batched into one call |
| Repeating a task | Same AI loop every time | **Replay a recorded skill: 0 AI calls** |
| Getting data | Click through the UI | **Call the site's own JSON API directly** |
| Simple pages | Launch a browser | Plain HTTP fetch first, browser only if needed |

Measured on the Hacker News front page (230 interactive elements): **2,412 tokens** in the compact format vs 6,667 as JSON.

## What makes it different

**1. Record once, replay instantly.** While the agent works, each action is saved with a stable element descriptor (id, name, placeholder, role and label, CSS path). Replaying runs those steps directly with no AI involved; a 5-step login-and-load flow replays in under a second in the tests. If the site has changed, replay stops at the broken step and returns the current page, so the AI only fixes what broke. Typed values can become parameters (`{{email}}`), and password fields are always stored as `{{password}}`, never as the real value.

**2. API discovery.** While browsing, every XHR/fetch call that returns JSON is catalogued: method, path template (`/api/users/{id}/orders`), query parameters, a redacted body example and the response shape. The agent can then call that endpoint directly with the browser's cookies, which takes milliseconds instead of a page interaction.

**3. Built for reading.** Images, fonts and media are blocked; pages are read only after JavaScript-rendered content has settled; and `read` skips the browser entirely for pages that plain HTTP can handle.

## How it works

```
 You ──chat──▶ Claude (the brain) ──MCP──▶ agentbrowser (the hands) ──▶ Chromium ──▶ websites
                   ▲                              │
                   └──── compact page text ◀──────┘
                          "e11 link Git for the US Code"
```

agentbrowser runs its own Chromium with a persistent profile, so it never touches your personal browser, and logins you make in it are kept between tasks.

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/channupraveen/agentbrowser
cd agentbrowser
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
pytest -s tests                    # runs against a bundled demo site
```

## Use it with Claude

### On your computer (Claude desktop app)

Open **Settings → Developer → Edit Config** (or edit `claude_desktop_config.json` directly) and add a server inside `"mcpServers"`:

```json
{
  "mcpServers": {
    "agentbrowser": {
      "command": "/path/to/agentbrowser/.venv/bin/python",
      "args": ["-m", "agentbrowser.mcp_server"],
      "env": {
        "AGENTBROWSER_DATA": "/path/to/agentbrowser/.agentbrowser",
        "AGENTBROWSER_HEADLESS": "0"
      }
    }
  }
}
```

On Windows the command is `C:\\path\\to\\agentbrowser\\.venv\\Scripts\\python.exe`. Fully quit and reopen Claude, then ask something like *"use agentbrowser to open news.ycombinator.com and summarise the top story"*.

### From any device (remote connector)

Local MCP servers only work in the desktop app on that machine. To use agentbrowser from your phone or the web app, serve it over HTTP behind HTTPS and add it as a custom connector.

**From your own computer, with a Cloudflare quick tunnel (Windows):**

```powershell
Invoke-WebRequest -Uri https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe -OutFile cloudflared.exe   # once
powershell -ExecutionPolicy Bypass -File .\start-connector.ps1
```

It prints a link like `https://<random>.trycloudflare.com/<secret>/mcp` and copies it to your clipboard. In Claude, go to **Settings → Connectors → Add custom connector** and paste it. Keep the window open and the computer awake. The quick-tunnel address changes on every restart; a named Cloudflare tunnel gives you a permanent one.

On macOS or Linux: `python -m agentbrowser.mcp_server --http` and `cloudflared tunnel --url http://127.0.0.1:8790`, then use `https://<tunnel-host>/<secret>/mcp`. The secret is in `.agentbrowser/mcp_token.txt`.

**Deployed on a server (Docker):**

```bash
docker build -t agentbrowser .
docker run -d -p 8790:8790 -v agentbrowser-data:/data \
  -e AGENTBROWSER_MCP_TOKEN="$(openssl rand -base64 24 | tr '+/' '-_' | tr -d '=')" \
  agentbrowser
```

Put it behind HTTPS (most hosting platforms do this for you) and add `https://<your-domain>/<token>/mcp` as a custom connector. Any platform that runs a Dockerfile and gives you a `PORT` works. A deployed instance browses from the server, so it has its own logins, not yours.

### MCP tools

| Tool | What it does |
|---|---|
| `read` | Fastest read of a page as text (HTTP first, browser only if needed) |
| `open` | Open a URL; returns elements with refs and the page text |
| `snapshot` | Current page, or only what changed with `diff=true` |
| `act` | One or more actions in a single call (click, type, press, select, goto, scroll, wait_for, back, check, uncheck) |
| `record_start` / `record_stop` | Record actions as a reusable skill, with optional parameters |
| `list_skills` / `replay` | List and replay skills with no AI reasoning |
| `list_apis` / `call_api` | See discovered JSON APIs and call them directly |

## Other ways to use it

### Playground (try it by hand)

```bash
uvicorn agentbrowser.server:app --port 8787
```

Open http://localhost:8787 to see exactly what an AI sees: token counts, element refs, and buttons to click, record and replay. Set `AGENTBROWSER_HEADLESS=0` to watch the Chromium window. You can also run it in GitHub Codespaces: **Code → Codespaces → Create codespace**, then open port 8787 from the Ports tab.

### HTTP API

| Method | Path | What it does |
|---|---|---|
| GET | `/read?url=` | Fastest read: HTTP first, browser fallback |
| GET | `/snapshot?diff=true` | Text and interactive elements (`e1`, `e2`, …) |
| POST | `/act` | One action, e.g. `{"action":"click","ref":"e3"}` |
| POST | `/batch` | Several actions in one round trip; returns a diff |
| POST | `/skills/record` | Start recording: `{"name":"login"}` |
| POST | `/skills/stop` | Save; `{"params":{"email":"me@x.com"}}` turns values into parameters |
| GET | `/skills` | List skills |
| POST | `/skills/{name}/replay` | Replay with no AI: `{"params":{"email":"…","password":"…"}}` |
| GET | `/apis?host=` | Discovered endpoints |
| POST | `/apis/call` | Call an endpoint with the browser's cookies |

### Python

```python
from agentbrowser import AgentBrowser

async with AgentBrowser() as b:
    await b.act({"action": "goto", "url": "https://example.com/login"})
    snap = await b.snapshot()          # snap["compact"] is the text to give your AI
    await b.record_start("login")
    await b.act_batch([{"action": "type", "ref": "e1", "text": "me@x.com"},
                       {"action": "type", "ref": "e2", "text": "secret"},
                       {"action": "click", "ref": "e3"}])
    await b.record_stop(params={"email": "me@x.com"})

    # Next time: no AI at all
    await b.replay("login", {"email": "me@x.com", "password": "secret"})
```

## What the AI sees

```
Shop login
http://127.0.0.1:8011/

elements:
e1 textbox Email
e2 textbox Password
e3 button Sign in

text:
Sign in
Email Password Sign in
```

After typing into the email field, the next snapshot only reports the change:

```
changed elements:
e1 textbox Email ="me@x.com"

text:
(unchanged)
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AGENTBROWSER_DATA` | `.agentbrowser` | Folder for the browser profile, skills, discovered APIs and the connector token |
| `AGENTBROWSER_HEADLESS` | `1` | `0` shows the Chromium window |
| `AGENTBROWSER_PROFILE` | `<data>/profile` | Browser profile folder (lets two servers run side by side) |
| `AGENTBROWSER_MCP_TOKEN` | generated | Secret path segment for the HTTP connector |
| `AGENTBROWSER_MCP_HOST` | `127.0.0.1` | HTTP bind address (`0.0.0.0` in Docker) |
| `AGENTBROWSER_MCP_PORT` / `PORT` | `8790` | HTTP port |

## Security

- agentbrowser controls a real browser. Anyone who can reach its MCP endpoint can browse as that browser, including any sites you're logged into in its profile. Treat the connector link as a password, and see [SECURITY.md](SECURITY.md).
- Skills never store password fields, and discovered API examples are redacted.
- Only use it on sites whose terms allow automation.

## Development

```bash
pip install -e ".[dev]"
playwright install chromium
pytest -s tests
```

Tests run against a small local demo site in `tests/demo_site.py`, covering fast read, record and replay, API discovery, hand-back when a site changes, and late JavaScript content. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- [x] MCP server for Claude, locally and as a remote connector
- [ ] Goal-aware snapshot pruning with a small local model
- [ ] Speculative prefetch of likely next links while the AI thinks
- [ ] Parallel tabs for fan-out tasks (building on [SwarmAI](https://github.com/channupraveen/Ai-swarm))
- [ ] Lightpanda engine option for lower memory, with Chromium fallback
- [ ] Self-healing replay: let the AI repair a broken step and save the fix
- [ ] Optional OAuth for the remote connector

## License

[MIT](LICENSE) © Channu Praveen Kumar
