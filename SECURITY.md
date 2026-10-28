# Security policy

## What to be careful about

agentbrowser drives a real browser on behalf of an AI agent. Keep these in mind:

- **The MCP connector link is a password.** Anyone with the HTTP connector URL (including its secret path) can browse as that browser, including sites logged in to in its profile. Don't share it or commit it. To rotate it, delete `.agentbrowser/mcp_token.txt` (or change `AGENTBROWSER_MCP_TOKEN`) and restart.
- **Logged-in sessions persist.** The browser profile keeps cookies between runs. Only log in to accounts you're comfortable letting your agent use.
- **The HTTP API and playground (`agentbrowser.server`) have no authentication.** Run them on localhost only; don't expose port 8787 to a network.
- **Skills and API catalogs** are stored as JSON in the data folder. Password fields are never recorded and discovered request bodies are redacted, but review them before sharing.

## Reporting a vulnerability

Please report security issues privately through GitHub: on this repository, go to **Security → Report a vulnerability**. Include steps to reproduce and the impact you see. You'll get a reply within a week.
