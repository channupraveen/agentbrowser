"""AgentBrowser: a browser session shaped for AI agents instead of humans.

- One persistent browser context, so logins and cookies survive between tasks
  (no reconnecting to Chrome for every job).
- Images, fonts and media are blocked by default: agents read, they don't look.
- Pages come back as compact text snapshots with element refs, not screenshots.
- Snapshots can be diffs, so follow-up turns send only what changed.
- Actions can be batched, recorded as skills, and replayed with no LLM.
- The site's own JSON APIs are discovered as you browse and can be called directly.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from . import locators
from .apis import ApiCatalog
from .fastread import fast_read
from .skills import SkillStore

SNAPSHOT_JS = (Path(__file__).parent / "snapshot.js").read_text()
BLOCKED_TYPES = {"image", "font", "media"}
ACTIONS = {"goto", "click", "type", "press", "select", "check", "uncheck", "scroll", "wait_for", "back"}


def approx_tokens(obj: Any) -> int:
    return len(str(obj)) // 4


class AgentBrowser:
    def __init__(self, data_dir: str | Path = ".agentbrowser", headless: bool = True,
                 block_resources: bool = True, action_timeout_ms: int = 5000):
        self.data_dir = Path(data_dir)
        self.headless = headless
        self.block_resources = block_resources
        self.timeout = action_timeout_ms
        self.skills = SkillStore(self.data_dir / "skills")
        self.apis = ApiCatalog(self.data_dir / "apis")
        self._pw = None
        self.context: BrowserContext | None = None
        self.tabs: dict[str, Page] = {}
        self._last: dict[str, dict] = {}

    # --- lifecycle -------------------------------------------------------
    async def start(self) -> "AgentBrowser":
        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            str(self.data_dir / "profile"), headless=self.headless,
            viewport={"width": 1280, "height": 900},
        )
        self.context.set_default_timeout(self.timeout)
        if self.block_resources:
            await self.context.route("**/*", self._route)
        self.context.on("response", self.apis.on_response)
        return self

    async def close(self) -> None:
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *exc):
        await self.close()

    @staticmethod
    async def _route(route):
        if route.request.resource_type in BLOCKED_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def tab(self, tab_id: str = "main") -> Page:
        page = self.tabs.get(tab_id)
        if page is None or page.is_closed():
            existing = [p for p in self.context.pages if p not in self.tabs.values()]
            page = existing[0] if existing else await self.context.new_page()
            self.tabs[tab_id] = page
        return page

    # --- reading ---------------------------------------------------------
    async def snapshot(self, tab: str = "main", max_text: int = 4000, diff: bool = False) -> dict:
        page = await self.tab(tab)
        snap = await page.evaluate(SNAPSHOT_JS, {"maxText": max_text})
        previous = self._last.get(tab)
        self._last[tab] = snap
        if diff and previous and previous["url"] == snap["url"]:
            old = {e["ref"]: e for e in previous["elements"]}
            new = {e["ref"]: e for e in snap["elements"]}
            out = {
                "url": snap["url"], "title": snap["title"], "diff": True,
                "added": [e for r, e in new.items() if r not in old],
                "changed": [e for r, e in new.items() if r in old and old[r] != e],
                "removed": [r for r in old if r not in new],
                "text": snap["text"] if snap["text"] != previous["text"] else "(unchanged)",
            }
        else:
            out = dict(snap, diff=False)
        out["tokens"] = approx_tokens(out)
        return out

    async def read(self, url: str, tab: str = "main", max_text: int = 8000) -> dict:
        """Fastest way to read a page: plain HTTP first, real browser only if needed."""
        t0 = time.perf_counter()
        try:
            result = await fast_read(url)
        except Exception:
            result = None
        if result is None:
            await self.act({"action": "goto", "url": url}, tab=tab)
            result = await self.snapshot(tab, max_text=max_text)
            result["via"] = "browser"
        else:
            result["text"] = result["text"][:max_text]
        result["ms"] = round((time.perf_counter() - t0) * 1000)
        return result

    # --- acting ----------------------------------------------------------
    async def act(self, action: dict, tab: str = "main") -> dict:
        name = action.get("action")
        if name not in ACTIONS:
            raise ValueError(f"unknown action {name!r}; expected one of {sorted(ACTIONS)}")
        page = await self.tab(tab)
        step: dict[str, Any] = {"action": name}

        if name == "goto":
            await page.goto(action["url"], wait_until="domcontentloaded")
            step["url"] = action["url"]
        elif name == "back":
            await page.go_back(wait_until="domcontentloaded")
        elif name == "press":
            await page.keyboard.press(action["key"])
            step["key"] = action["key"]
        elif name == "scroll":
            await page.mouse.wheel(0, action.get("dy", 800))
            step["dy"] = action.get("dy", 800)
        elif name == "wait_for":
            await page.get_by_text(action["text"]).first.wait_for(timeout=action.get("timeout_ms", self.timeout))
            step["text"] = action["text"]
        else:
            ref = action["ref"]
            target = page.locator(f'[data-ab-ref="{ref}"]').first
            desc = await locators.describe(page, ref)
            step["target"] = desc
            if name == "click":
                await target.click()
            elif name == "type":
                text = action["text"]
                await target.fill(text)
                is_secret = desc.get("type") == "password"
                step["text"] = "{{password}}" if is_secret else text
            elif name == "select":
                await target.select_option(action["value"])
                step["value"] = action["value"]
            elif name == "check":
                await target.check()
            elif name == "uncheck":
                await target.uncheck()

        self.skills.add(step)
        return {"ok": True, "action": name, "url": page.url}

    async def act_batch(self, actions: list[dict], tab: str = "main", snapshot: bool = True) -> dict:
        """Run several actions in one round-trip (fill a whole form, then submit)."""
        results = []
        for i, a in enumerate(actions):
            try:
                results.append(await self.act(a, tab=tab))
            except Exception as e:
                results.append({"ok": False, "action": a.get("action"), "error": str(e)[:300]})
                return {"ok": False, "failed_at": i, "results": results,
                        "snapshot": await self.snapshot(tab) if snapshot else None}
        return {"ok": True, "results": results,
                "snapshot": await self.snapshot(tab, diff=True) if snapshot else None}

    # --- skills: record once, replay instantly -----------------------------
    async def record_start(self, name: str, tab: str = "main") -> dict:
        page = await self.tab(tab)
        url = page.url if page.url != "about:blank" else None
        self.skills.start(name, url)
        return {"recording": name, "start_url": url}

    async def record_stop(self, params: dict[str, str] | None = None, description: str = "") -> dict:
        return self.skills.stop(params, description)

    async def replay(self, name: str, params: dict[str, str] | None = None, tab: str = "main") -> dict:
        skill = self.skills.get(name)
        params = params or {}
        page = await self.tab(tab)
        t0 = time.perf_counter()
        if skill.get("start_url"):
            await page.goto(skill["start_url"], wait_until="domcontentloaded")
        for i, step in enumerate(skill["steps"]):
            try:
                await self._run_step(page, step, params)
            except Exception as e:
                # Hand back to the agent exactly where the site diverged.
                return {"ok": False, "skill": name, "failed_step": i, "step": step,
                        "error": str(e)[:300], "snapshot": await self.snapshot(tab),
                        "ms": round((time.perf_counter() - t0) * 1000)}
        return {"ok": True, "skill": name, "steps": len(skill["steps"]), "llm_calls": 0,
                "url": page.url, "ms": round((time.perf_counter() - t0) * 1000)}

    async def _run_step(self, page: Page, step: dict, params: dict[str, str]) -> None:
        name = step["action"]
        if name == "goto":
            await page.goto(self.skills.fill(step["url"], params), wait_until="domcontentloaded")
        elif name == "back":
            await page.go_back(wait_until="domcontentloaded")
        elif name == "press":
            await page.keyboard.press(step["key"])
        elif name == "scroll":
            await page.mouse.wheel(0, step.get("dy", 800))
        elif name == "wait_for":
            await page.get_by_text(self.skills.fill(step["text"], params)).first.wait_for()
        else:
            target = await locators.resolve(page, step["target"], self.timeout)
            if name == "click":
                await target.click()
            elif name == "type":
                await target.fill(self.skills.fill(step["text"], params))
            elif name == "select":
                await target.select_option(step["value"])
            elif name == "check":
                await target.check()
            elif name == "uncheck":
                await target.uncheck()

    # --- API discovery ----------------------------------------------------
    def list_apis(self, host: str | None = None) -> list[dict]:
        return self.apis.list(host)

    async def call_api(self, method: str, url: str, params: dict | None = None,
                       json: Any = None, headers: dict | None = None) -> dict:
        """Call a discovered endpoint directly, using the browser's cookies."""
        t0 = time.perf_counter()
        resp = await self.context.request.fetch(url, method=method.upper(), params=params,
                                                data=json, headers=headers)
        try:
            body = await resp.json()
        except Exception:
            body = (await resp.text())[:4000]
        return {"status": resp.status, "body": body, "ms": round((time.perf_counter() - t0) * 1000)}
