"""A tiny local site for tests and demos: login form -> dashboard that loads orders via fetch()."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOGIN = """<!doctype html><html><head><title>Shop login</title></head><body>
<h1>Sign in</h1>
<form action="/dashboard" method="get">
  <label for="email">Email</label><input id="email" name="email" placeholder="you@example.com">
  <label for="pw">Password</label><input id="pw" name="pw" type="password">
  <button type="submit">Sign in</button>
</form></body></html>"""

DASHBOARD = """<!doctype html><html><head><title>Dashboard</title></head><body>
<h1>Welcome</h1><p id="who"></p>
<button id="load">Load orders</button>
<ul id="orders"></ul>
<script>
  document.getElementById('who').innerText = 'Signed in as ' + new URLSearchParams(location.search).get('email');
  document.getElementById('load').onclick = async () => {
    const r = await fetch('/api/users/42/orders?status=open');
    const data = await r.json();
    document.getElementById('orders').innerHTML = data.orders.map(o => `<li>${o.item} - ${o.price}</li>`).join('');
  };
</script></body></html>"""

ARTICLE = "<!doctype html><html><head><title>Static article</title></head><body><h1>Hello</h1>" + (
    "<p>This page is plain HTML, so it can be read without a browser.</p>" * 10) + "</body></html>"

SPA = '<!doctype html><html><head><title>SPA</title></head><body><div id="root"></div><script>' \
      'document.getElementById("root").innerHTML = "<h1>Rendered by JS</h1>" + "<p>client side text</p>".repeat(20);' \
      '</script></body></html>'

LATE = '<!doctype html><html><head><title>Late article</title></head><body><main id="m"></main><script>' \
       'setTimeout(() => { document.getElementById("m").innerHTML = "<h1>Loaded later</h1><p>This article text arrives 700 ms after the page.</p>"; }, 700);' \
       '</script></body></html>'

HOME = '<!doctype html><html><head><title>Home</title></head><body><a href="/late">Read the article</a></body></html>'

ORDERS = {"orders": [{"id": 1, "item": "Rice 5kg", "price": 420}, {"id": 2, "item": "Dal 1kg", "price": 150}]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        routes = {"/": LOGIN, "/dashboard": DASHBOARD, "/article": ARTICLE, "/spa": SPA,
                  "/late": LATE, "/home": HOME}
        if path in routes:
            body, ctype = routes[path].encode(), "text/html; charset=utf-8"
        elif path.startswith("/api/users/") and path.endswith("/orders"):
            body, ctype = json.dumps(ORDERS).encode(), "application/json"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    srv, url = serve(8000)
    print("demo site on", url)
    threading.Event().wait()
