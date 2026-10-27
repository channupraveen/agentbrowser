"""Fetch-first reading: most pages don't need a browser at all.

A plain HTTP GET plus HTML-to-text takes tens of milliseconds. We only fall
back to the real browser when the page is clearly rendered by JavaScript.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx

SKIP = {"script", "style", "noscript", "svg", "head", "template", "iframe"}
INLINE_GAP = {"a", "span", "td", "th", "button", "label", "b", "strong", "em", "i", "small"}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "section",
         "article", "header", "footer", "ul", "ol", "table", "pre", "blockquote"}
JS_SHELL_HINTS = re.compile(r'id="(root|app|__next|__nuxt)"\s*>\s*</div>|enable javascript', re.I)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.links: list[dict] = []
        self.title = ""
        self._skip = 0
        self._in_title = False
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in BLOCK:
            self.out.append("\n")
        elif tag in INLINE_GAP:
            self.out.append(" ")
        if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
            self.out.append("#" * int(tag[1]) + " ")
        if tag == "li":
            self.out.append("- ")
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href:
            text = " ".join("".join(self._link_text).split())
            if text and len(self.links) < 200:
                self.links.append({"text": text[:80], "href": self._href})
            self._href = None
        if tag in BLOCK:
            self.out.append("\n")
        elif tag in INLINE_GAP:
            self.out.append(" ")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._skip:
            return
        self.out.append(data)
        if self._href is not None:
            self._link_text.append(data)


def html_to_text(html: str) -> tuple[str, str, list[dict]]:
    p = _Text()
    p.feed(html)
    text = "".join(p.out)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return p.title.strip(), text.strip(), p.links


async def fast_read(url: str, timeout: float = 10.0) -> dict | None:
    """Return a readable view of the page, or None if it needs a real browser."""
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 agentbrowser"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
        r = await client.get(url)
    if "html" not in r.headers.get("content-type", ""):
        return None
    title, text, links = html_to_text(r.text)
    if len(text) < 200 or JS_SHELL_HINTS.search(r.text):
        return None
    return {"url": str(r.url), "title": title, "text": text, "links": links, "via": "http"}
