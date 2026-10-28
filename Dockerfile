FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    AGENTBROWSER_DATA=/data \
    AGENTBROWSER_HEADLESS=1 \
    AGENTBROWSER_MCP_HOST=0.0.0.0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY agentbrowser ./agentbrowser

# Installs the Chromium build that matches the installed Playwright version, plus its system libraries.
RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

VOLUME /data
EXPOSE 8790

# Set AGENTBROWSER_MCP_TOKEN so the connector URL stays the same across restarts.
CMD ["agentbrowser-mcp", "--http"]
