# agentbrowser

**The browser that learns: the first run uses AI, every run after is instant.**

Most AI browser agents are slow for the same reason: every step is screenshot → vision model → click → screenshot. agentbrowser gives agents a text view of the web instead, and then removes the model from the loop wherever it can.

| | Typical agent browser | agentbrowser |
|---|---|---|
| What the model sees | Screenshots | Compact text snapshot with element refs (a login page ≈ 76 tokens) |
| Follow-up turns | Full page again | Diff: only what changed |
| Repeating a task | Same LLM loop every time | **Replay a recorded skill: 0 LLM calls** |
| Getting data | Click through the UI | **Call the site's own JSON API directly** |
| Simple pages | Launch a browser | Plain HTTP fetch first, browser only if needed |
| Session | Reconnect to Chrome per task | One persistent profile, logins survive |

## The two ideas that make it different

**1. Record once, replay instantly (skills).** While the agent works, every action is saved with a stable element descriptor (id, name, placeholder, role + label, CSS path). Replay runs those steps directly. In the tests, a 5-step login-and-load flow replays in ~230 ms with zero LLM calls. If the site changed, replay stops at the broken step and hands the agent a fresh snapshot, so the AI only fixes the part that broke. Typed values can become parameters (`{{email}}`), and password fields are always saved as `{{password}}`, never as the real value.

**2. API discovery.** While the agent browses, every XHR/fetch that returns JSON is catalogued as an endpoint: method, path template (`/api/users/{id}/orders`), query params, redacted body example and response shape. Next time the agent can call that endpoint directly with the browser's cookies. In the tests that's ~15 ms instead of a full page interaction.

## Try it in 2 minutes (works from a phone)

1. On this repo, tap **Code → Codespaces → Create codespace on main**. (On a phone, switch your browser to "Desktop site" first.)
2. Wait for setup to finish. It installs everything and starts the server.
3. Open the **Ports** tab, then the globe icon next to port **8787**. The playground opens.
4. Enter a URL and tap **Fast read** or **Open in browser**. Then tap elements, record a skill, and replay it with no AI.

## Quick start

```bash
pip install -e ".[dev]"
playwright install chromium
pytest -s tests            # runs against a bundled demo site
uvicorn agentbrowser.server:app --port 8787
```

### HTTP API

| Method | Path | What it does |
|---|---|---|
| GET | `/read?url=` | Fastest read: HTTP first, browser fallback |
| GET | `/snapshot?diff=true` | Text + interactive elements (`e1`, `e2`, …) |
| POST | `/act` | One action: `{"action":"click","ref":"e3"}` |
| POST | `/batch` | Several actions in one round-trip, returns a diff |
| POST | `/skills/record` | Start recording `{"name":"login"}` |
| POST | `/skills/stop` | Save it, `{"params":{"email":"me@x.com"}}` turns values into parameters |
| GET | `/skills` | List skills |
| POST | `/skills/{name}/replay` | Run with no LLM: `{"params":{"email":"…","password":"…"}}` |
| GET | `/apis?host=` | Discovered endpoints |
| POST | `/apis/call` | Call one directly with the session's cookies |

Actions: `goto`, `click`, `type`, `press`, `select`, `check`, `uncheck`, `scroll`, `wait_for`, `back`.

### Python

```python
from agentbrowser import AgentBrowser

async with AgentBrowser() as b:
    await b.act({"action": "goto", "url": "https://example.com/login"})
    snap = await b.snapshot()                      # give this to your LLM
    await b.record_start("login")
    await b.act_batch([{"action": "type", "ref": "e1", "text": "me@x.com"},
                       {"action": "type", "ref": "e2", "text": "secret"},
                       {"action": "click", "ref": "e3"}])
    await b.record_stop(params={"email": "me@x.com"})

    # Next time: no LLM at all
    await b.replay("login", {"email": "me@x.com", "password": "secret"})
```

See `examples/agent.py` for a full agent loop with OpenAI or Groq.

## Example snapshot

```json
{"url": "http://127.0.0.1:8011/", "title": "Shop login",
 "text": "Sign in\nEmail Password Sign in",
 "elements": [{"ref": "e1", "role": "textbox", "name": "Email"},
              {"ref": "e2", "role": "textbox", "name": "Password"},
              {"ref": "e3", "role": "button", "name": "Sign in"}],
 "tokens": 76}
```

## Roadmap

- [ ] MCP server so Claude Desktop / Claude Code can use it directly
- [ ] Goal-aware snapshot pruning with a small local model
- [ ] Speculative prefetch of likely next links while the LLM thinks
- [ ] Parallel tab swarm for fan-out tasks (building on [SwarmAI](https://github.com/channupraveen/Ai-swarm))
- [ ] Lightpanda engine option for lower memory, with Chromium fallback
- [ ] Self-healing replay: let the LLM repair a broken step and save the fix

## License

MIT
