"""HTTP API so any agent (Claude, local models, SwarmAI) can drive the browser.

Run:  uvicorn agentbrowser.server:app --port 8787
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .browser import AgentBrowser

browser = AgentBrowser(
    data_dir=os.getenv("AGENTBROWSER_DATA", ".agentbrowser"),
    headless=os.getenv("AGENTBROWSER_HEADLESS", "1") != "0",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await browser.start()
    yield
    await browser.close()


app = FastAPI(title="agentbrowser", version="0.1.0", lifespan=lifespan)


class Action(BaseModel):
    action: str
    ref: str | None = None
    url: str | None = None
    text: str | None = None
    key: str | None = None
    value: str | None = None
    dy: int | None = None
    timeout_ms: int | None = None


class Batch(BaseModel):
    actions: list[Action]
    tab: str = "main"
    snapshot: bool = True


class RecordStart(BaseModel):
    name: str
    tab: str = "main"


class RecordStop(BaseModel):
    params: dict[str, str] = Field(default_factory=dict,
                                   description="param name -> literal value typed while recording")
    description: str = ""


class Replay(BaseModel):
    params: dict[str, str] = Field(default_factory=dict)
    tab: str = "main"


class ApiCall(BaseModel):
    method: str = "GET"
    url: str
    params: dict[str, Any] | None = None
    json_body: Any = None
    headers: dict[str, str] | None = None


def _clean(a: Action) -> dict:
    return {k: v for k, v in a.model_dump().items() if v is not None}


PLAYGROUND = (Path(__file__).parent / "playground.html").read_text()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def playground():
    return PLAYGROUND


@app.get("/read")
async def read(url: str, tab: str = "main", max_text: int = 8000):
    return await browser.read(url, tab=tab, max_text=max_text)


@app.get("/snapshot")
async def snapshot(tab: str = "main", diff: bool = False, max_text: int = 4000):
    return await browser.snapshot(tab, max_text=max_text, diff=diff)


@app.post("/act")
async def act(action: Action, tab: str = "main", snapshot: bool = True):
    return await browser.act_batch([_clean(action)], tab=tab, snapshot=snapshot)


@app.post("/batch")
async def batch(body: Batch):
    return await browser.act_batch([_clean(a) for a in body.actions], tab=body.tab, snapshot=body.snapshot)


@app.post("/skills/record")
async def record_start(body: RecordStart):
    return await browser.record_start(body.name, tab=body.tab)


@app.post("/skills/stop")
async def record_stop(body: RecordStop):
    try:
        return await browser.record_stop(body.params, body.description)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/skills")
async def list_skills():
    return browser.skills.list()


@app.post("/skills/{name}/replay")
async def replay(name: str, body: Replay):
    try:
        return await browser.replay(name, body.params, tab=body.tab)
    except KeyError as e:
        raise HTTPException(404, f"no skill or parameter: {e}")


@app.get("/apis")
async def list_apis(host: str | None = None):
    return browser.list_apis(host)


@app.post("/apis/call")
async def call_api(body: ApiCall):
    return await browser.call_api(body.method, body.url, body.params, body.json_body, body.headers)
