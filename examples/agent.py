"""Minimal agent loop: an LLM (OpenAI or Groq) + agentbrowser.

    # OpenAI (used when OPENAI_API_KEY is set)
    export OPENAI_API_KEY=...        # PowerShell: $env:OPENAI_API_KEY="..."
    # or Groq
    export GROQ_API_KEY=...

    python examples/agent.py "https://news.ycombinator.com" "Open the top story and tell me its title"

The model sees compact text snapshots (not screenshots) and can send several
actions per turn. Set RECORD=name to save the run as a replayable skill.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

from agentbrowser import AgentBrowser

if os.getenv("OPENAI_API_KEY"):
    PROVIDER, API_URL, API_KEY = "OpenAI", "https://api.openai.com/v1/chat/completions", os.environ["OPENAI_API_KEY"]
    MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
elif os.getenv("GROQ_API_KEY"):
    PROVIDER, API_URL, API_KEY = "Groq", "https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"]
    MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
else:
    sys.exit("Set OPENAI_API_KEY or GROQ_API_KEY first.")
SYSTEM = """You control a web browser. Each turn you get a page snapshot: text plus
interactive elements with refs (e1, e2...). Reply with JSON only:
{"actions": [{"action": "click", "ref": "e3"}, {"action": "type", "ref": "e5", "text": "..."}]}
Actions: goto(url), click(ref), type(ref,text), press(key), select(ref,value), scroll(dy),
wait_for(text), back. Send several actions at once when you can (e.g. fill a whole form).
When the task is done reply {"done": true, "answer": "..."}."""


async def llm(messages: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            API_URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": MODEL, "messages": messages, "temperature": 0,
                  "response_format": {"type": "json_object"}},
        )
        if r.status_code >= 400:
            sys.exit(f"{PROVIDER} API error {r.status_code}: {r.text[:300]}")
        return json.loads(r.json()["choices"][0]["message"]["content"])


async def main(url: str, task: str, max_turns: int = 12) -> None:
    print(f"Using {PROVIDER} ({MODEL}). The browser is Chromium, driven by agentbrowser.")
    async with AgentBrowser(headless=os.getenv("AGENTBROWSER_HEADLESS", "1") != "0") as b:
        await b.act({"action": "goto", "url": url})
        if os.getenv("RECORD"):
            await b.record_start(os.environ["RECORD"])
        snap = await b.snapshot()
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Task: {task}\n\nPage:\n{snap['compact']}"}]
        for turn in range(max_turns):
            reply = await llm(messages)
            messages.append({"role": "assistant", "content": json.dumps(reply)})
            if reply.get("done"):
                print("\nANSWER:", reply.get("answer"))
                break
            result = await b.act_batch(reply.get("actions", []))
            page = result["snapshot"]["compact"] if result["snapshot"] else ""
            status = "ok" if result["ok"] else f"failed at action {result['failed_at']}: {result['results'][-1]['error']}"
            print(f"turn {turn + 1}: {reply.get('actions')} -> {status} ({result['snapshot']['compact_tokens']} tokens back)")
            messages.append({"role": "user", "content": f"{status}\n\nPage:\n{page}"})
        if os.getenv("RECORD"):
            skill = await b.record_stop(description=task)
            print(f"saved skill '{skill['name']}' with {len(skill['steps'])} steps; replay it with no LLM.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
