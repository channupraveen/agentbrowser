"""Stable element descriptors, so a recorded action still finds its element on replay.

Refs like e3 only live as long as the page. When we record a skill we save a
descriptor (id, name attribute, placeholder, role + accessible name, CSS path) and
on replay try each strategy until exactly one element matches.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import Locator, Page

DESCRIBE_JS = r"""
(el) => {
  const tag = el.tagName.toLowerCase();
  const role = (() => {
    const r = el.getAttribute('role');
    if (r) return r;
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (['submit', 'button', 'reset', 'image'].includes(t)) return 'button';
      if (t === 'checkbox' || t === 'radio') return t;
      return 'textbox';
    }
    return null;
  })();
  let name = el.getAttribute('aria-label') || '';
  if (!name && el.id) {
    const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lab) name = lab.innerText;
  }
  if (!name && tag === 'input' && ['submit', 'button'].includes(el.type)) name = el.value;
  if (!name && ['a', 'button', 'summary'].includes(tag)) name = el.innerText;
  const path = [];
  let node = el;
  while (node && node.nodeType === 1 && node !== document.body && path.length < 6) {
    let part = node.tagName.toLowerCase();
    const parent = node.parentElement;
    if (parent) {
      const same = Array.from(parent.children).filter(c => c.tagName === node.tagName);
      if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
    }
    path.unshift(part);
    node = parent;
  }
  return {
    tag,
    id: el.id || null,
    name_attr: el.getAttribute('name'),
    placeholder: el.getAttribute('placeholder'),
    type: el.getAttribute('type'),
    role,
    name: (name || '').trim().replace(/\s+/g, ' ').slice(0, 80) || null,
    css: path.join(' > '),
  };
}
"""


def _css_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def describe(page: Page, ref: str) -> dict:
    return await page.locator(f'[data-ab-ref="{ref}"]').first.evaluate(DESCRIBE_JS)


def candidates(page: Page, d: dict) -> list[Locator]:
    tag = d.get("tag") or "*"
    out: list[Locator] = []
    if d.get("id"):
        out.append(page.locator(f'[id="{_css_str(d["id"])}"]'))
    if d.get("name_attr"):
        out.append(page.locator(f'{tag}[name="{_css_str(d["name_attr"])}"]'))
    if d.get("placeholder"):
        out.append(page.locator(f'{tag}[placeholder="{_css_str(d["placeholder"])}"]'))
    if d.get("role") and d.get("name"):
        out.append(page.get_by_role(d["role"], name=d["name"], exact=True))
    if d.get("css"):
        out.append(page.locator(d["css"]))
    return out


async def resolve(page: Page, d: dict, timeout_ms: int = 3000) -> Locator:
    """Return the first strategy that matches exactly one element."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    while True:
        for loc in candidates(page, d):
            try:
                if await loc.count() == 1:
                    return loc
            except Exception:
                continue
        if loop.time() >= deadline:
            raise LookupError(f"element not found: {d}")
        await asyncio.sleep(0.1)
