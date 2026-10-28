# Contributing to agentbrowser

Thanks for your interest! Bug reports, ideas and pull requests are all welcome.

## Getting set up

```bash
git clone https://github.com/channupraveen/agentbrowser
cd agentbrowser
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
pytest -s tests
```

The tests run against a small local site in `tests/demo_site.py`, so they don't depend on the internet.

## Making a change

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Create a branch, make your change, and add or update a test in `tests/` that covers it.
3. Run `pytest -s tests` and make sure everything passes.
4. Open a pull request describing what changed and why.

## Where things live

| File | What it does |
|---|---|
| `agentbrowser/browser.py` | Core: browser session, snapshots, actions, replay, settle logic |
| `agentbrowser/snapshot.js` | Runs in the page; builds the element list and text |
| `agentbrowser/locators.py` | Stable element descriptors used by recorded skills |
| `agentbrowser/skills.py` | Recording, parameters and the skill library |
| `agentbrowser/apis.py` | API discovery from network traffic |
| `agentbrowser/fastread.py` | HTTP-only reading without a browser |
| `agentbrowser/mcp_server.py` | MCP server (stdio and HTTP) |
| `agentbrowser/server.py`, `playground.html` | HTTP API and the playground page |

## Guidelines

- Keep what the AI receives compact: every token in a snapshot is paid for on every step.
- Never store secrets: password fields in skills, or credentials in discovered API examples.
- Prefer small, focused pull requests.

## Reporting security issues

Please don't open a public issue for security problems. See [SECURITY.md](SECURITY.md).
