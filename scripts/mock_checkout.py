"""Fake DGePay checkout page. The API talks to this (:18081) instead of mock_dgepay.py (:18080): every call is forwarded
unchanged, except that initiate_payment's webview_url is rewritten to a page served here with Pay / Fail buttons.
Pressing one sets the result on the mock, then sends the browser to the API callback, which redirects to the web portal."""
import json, sys, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MOCK, SELF, API = "http://127.0.0.1:18080", "http://localhost:18081", "http://localhost:9096"
PAGE = """<!doctype html><meta charset=utf-8><title>Mock DGePay</title><body style="font-family:sans-serif;max-width:360px;margin:60px auto">
<h2>Mock DGePay checkout</h2><p>Payment <code>{id}</code></p>
<p><a href="/done/{id}?ok=1"><button style="padding:10px 24px">Pay</button></a>
<a href="/done/{id}?ok=0"><button style="padding:10px 24px">Fail</button></a></p>"""


class H(BaseHTTPRequestHandler):
    def forward(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        req = urllib.request.Request(MOCK + self.path, body, {k: v for k, v in self.headers.items() if k.lower() != "host"}, method=self.command)
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            r = e
        data = r.read()
        if self.path.endswith("/initiate_payment") and r.status == 200:
            j = json.loads(data)
            j["data"]["webview_url"] = f"{SELF}/pay/{j['data']['unique_txn_id']}"
            data = json.dumps(j).encode()
        self.send_response(r.status)
        self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_POST = forward

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path.startswith("/pay/"):
            out = PAGE.format(id=path[5:]).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
        elif path.startswith("/done/"):
            tid = path[6:]
            res = json.dumps({"unique_txn_id": tid, "status_code": 3 if query == "ok=1" else 4}).encode()
            urllib.request.urlopen(urllib.request.Request(MOCK + "/mock/result", res, {"Content-Type": "application/json"}))
            self.send_response(302); self.send_header("Location", f"{API}/ticket-booking/payment/callback/{tid}"); self.end_headers()
        else:
            self.forward()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18081), H).serve_forever()
