"""Minimal agent loop: Groq LLM + agentbrowser.

    export GROQ_API_KEY=...
    python examples/groq_agent.py "https://news.ycombinator.com" "Open the top story and summarize it"

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

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SYSTEM = """You control a web browser. Each turn you get a page snapshot: text plus
interactive elements with refs (e1, e2...). Reply with JSON only:
{"actions": [{"action": "click", "ref": "e3"}, {"action": "type", "ref": "e5", "text": "..."}]}
Actions: goto(url), click(ref), type(ref,text), press(key), select(ref,value), scroll(dy),
wait_for(text), back. Send several actions at once when you can (e.g. fill a whole form).
When the task is done reply {"done": true, "answer": "..."}."""


async def llm(messages: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json={"model": MODEL, "messages": messages, "temperature": 0,
                  "response_format": {"type": "json_object"}},
        )
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


async def main(url: str, task: str, max_turns: int = 12) -> None:
    async with AgentBrowser() as b:
        await b.act({"action": "goto", "url": url})
        if os.getenv("RECORD"):
            await b.record_start(os.environ["RECORD"])
        snap = await b.snapshot()
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Task: {task}\n\nPage:\n{json.dumps(snap)}"}]
        for turn in range(max_turns):
            reply = await llm(messages)
            messages.append({"role": "assistant", "content": json.dumps(reply)})
            if reply.get("done"):
                print("\nANSWER:", reply.get("answer"))
                break
            result = await b.act_batch(reply.get("actions", []))
            print(f"turn {turn + 1}: {reply.get('actions')} -> ok={result['ok']} "
                  f"({result['snapshot']['tokens']} tokens back)")
            messages.append({"role": "user", "content": json.dumps(result)})
        if os.getenv("RECORD"):
            skill = await b.record_stop(description=task)
            print(f"saved skill '{skill['name']}' with {len(skill['steps'])} steps; replay it with no LLM.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
