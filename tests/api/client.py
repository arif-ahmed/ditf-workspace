"""HTTP + AES helper for the DITF APIs. Records every call so the report can show it."""
import base64, json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PUBLIC = os.environ.get("DITF_PUBLIC_URL", "http://127.0.0.1:9096") + "/ticket-booking"
ADMIN = os.environ.get("DITF_ADMIN_URL", "http://127.0.0.1:9097") + "/ticket-booking"
MOCK = "http://127.0.0.1:18080"
DB_CONTAINER = os.environ.get("DITF_DB_CONTAINER", "ditf-pg")
MERCHANT_ID = "1502418a38c547ed90d55e2028fe3fc4"  # from scripts/seed/seed.sql

_props = os.path.join(ROOT, "dg-tms-api", "src", "main", "resources", "application.properties")
_key = [l.split("=", 1)[1].strip() for l in open(_props, encoding="utf-8") if l.strip().startswith("platform_secret_key")][-1]
KEY = _key.encode()[:16].ljust(16, b"\0")

trace = []  # calls made by the case that is running; the runner empties it between cases


def enc(obj):
    p = padding.PKCS7(128).padder()
    d = p.update(json.dumps(obj).encode()) + p.finalize()
    e = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
    return base64.b64encode(e.update(d) + e.finalize()).decode()


def dec(b64):
    d = Cipher(algorithms.AES(KEY), modes.ECB()).decryptor()
    raw = d.update(base64.b64decode(b64)) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    return json.loads(u.update(raw) + u.finalize())


def _mask(v):
    s = json.dumps(v) if not isinstance(v, str) else v
    return re.sub(r'("(?:login_pin|token|client_secret_key|client_api_key)"\s*:\s*")[^"]+', r'\1***', s)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def call(base, method, path, body=None, token=None, params=None, headers=None, encrypted=False):
    """Returns Resp. body dict is sent as JSON (or AES text when encrypted=True); `data` in the reply is decrypted."""
    url = (path if path.startswith("http") else base + path) + ("?" + urllib.parse.urlencode(params) if params else "")
    data = None if body is None else (enc(body) if encrypted else json.dumps(body)).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "text/plain" if encrypted else "application/json")
    if token:
        req.add_header("Authorization", "Token " + token)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    t0 = time.perf_counter()
    try:
        r = _opener.open(req, timeout=90)
        status, hdrs, text = r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        status, hdrs, text = e.code, dict(e.headers), e.read().decode()
    ms = round((time.perf_counter() - t0) * 1000)
    try:
        j = json.loads(text) if text else {}
    except ValueError:
        j = {"raw": text}
    if isinstance(j, dict) and isinstance(j.get("data"), str):
        try:
            j["data"] = dec(j["data"])
        except Exception:
            pass
    resp = Resp(status, j, hdrs, ms)
    trace.append({"method": method, "url": url, "status": status, "ms": ms,
                  "request": _mask(body) if body is not None else "", "response": _mask(j)[:4000]})
    return resp


class Resp:
    def __init__(self, status, json_, headers, ms):
        self.status, self.json, self.headers, self.ms = status, json_ if isinstance(json_, dict) else {}, headers, ms

    @property
    def data(self):
        return self.json.get("data") or {}

    @property
    def error(self):
        e = self.json.get("error")
        return e[0] if isinstance(e, list) and e else e


def pub(method, path, **kw):
    return call(PUBLIC, method, path, **kw)


def adm(method, path, **kw):
    return call(ADMIN, method, path, **kw)


def login(phone, pin="1234"):
    return adm("POST", "/verify-login-pin", body={"phone_number": phone, "login_pin": pin})


def sql(query):
    """Fact-check against the dev database (read-mostly)."""
    return subprocess.check_output(["docker", "exec", DB_CONTAINER, "psql", "-U", "ditf", "-d", "ditf", "-At", "-v", "ON_ERROR_STOP=1", "-c", query]).decode().strip()


def mock(path, obj=None):
    req = urllib.request.Request(MOCK + path, data=None if obj is None else json.dumps(obj).encode(), method="GET" if obj is None else "POST")
    req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode() or "{}")
