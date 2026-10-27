"""Record once, replay instantly.

While recording, every action the agent takes is saved with a stable element
descriptor. Replaying a skill runs those steps directly, with no LLM calls. If a
step fails (the site changed), replay stops and returns a fresh snapshot so the
agent can take over from exactly that point.

Typed values can be turned into parameters ({{email}}). Password fields are
always stored as {{password}}, never as the real value.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

PARAM = re.compile(r"\{\{(\w+)\}\}")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "skill"


class SkillStore:
    def __init__(self, store: Path):
        self.store = store
        self.store.mkdir(parents=True, exist_ok=True)
        self.recording: dict | None = None

    # --- recording -------------------------------------------------------
    def start(self, name: str, start_url: str | None) -> None:
        self.recording = {"name": name, "start_url": start_url, "steps": [], "created": int(time.time())}

    def add(self, step: dict) -> None:
        if self.recording is not None:
            self.recording["steps"].append(step)

    def stop(self, params: dict[str, str] | None = None, description: str = "") -> dict:
        if self.recording is None:
            raise RuntimeError("not recording")
        skill, self.recording = self.recording, None
        params = params or {}
        for step in skill["steps"]:
            if step.get("text") is None:
                continue
            for pname, literal in params.items():
                if literal and step["text"] == literal:
                    step["text"] = "{{" + pname + "}}"
        skill["description"] = description
        skill["params"] = sorted({p for s in skill["steps"] for p in PARAM.findall(s.get("text") or "")})
        (self.store / f"{slug(skill['name'])}.json").write_text(json.dumps(skill, indent=2))
        return skill

    # --- library ---------------------------------------------------------
    def get(self, name: str) -> dict:
        path = self.store / f"{slug(name)}.json"
        if not path.exists():
            raise KeyError(name)
        return json.loads(path.read_text())

    def list(self) -> list[dict]:
        out = []
        for f in sorted(self.store.glob("*.json")):
            s = json.loads(f.read_text())
            out.append({"name": s["name"], "description": s.get("description", ""),
                        "params": s.get("params", []), "steps": len(s["steps"])})
        return out

    @staticmethod
    def fill(text: str | None, values: dict[str, str]) -> str | None:
        if text is None:
            return None

        def sub(m: re.Match) -> str:
            if m.group(1) not in values:
                raise KeyError(f"missing parameter: {m.group(1)}")
            return values[m.group(1)]

        return PARAM.sub(sub, text)
